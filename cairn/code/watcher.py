"""Filesystem watcher for automatic code re-indexing.

Monitors directories under CAIRN_CODE_DIR for changes and triggers
incremental re-indexing. Uses per-path debouncing to coalesce rapid
filesystem events (IDE saves, git operations).

Thread safety: all indexing runs on a single dedicated worker thread
via a queue, preventing concurrent graph writes.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# How long to wait after the last filesystem event before triggering re-index.
_DEBOUNCE_SECONDS = 3.0


class _IndexRequest:
    """A request to re-index a project after filesystem changes."""

    __slots__ = ("project", "project_id", "root")

    def __init__(self, project: str, project_id: int, root: Path) -> None:
        self.project = project
        self.project_id = project_id
        self.root = root


class _ProjectEventHandler(FileSystemEventHandler):
    """Handles filesystem events for a single watched project.

    Debounces events per project — a burst of saves within the debounce
    window collapses into a single re-index request.
    """

    def __init__(
        self,
        project: str,
        project_id: int,
        root: Path,
        queue: Queue[_IndexRequest],
        supported_extensions: frozenset[str],
    ) -> None:
        super().__init__()
        self.project = project
        self.project_id = project_id
        self.root = root
        self._queue = queue
        self._extensions = supported_extensions
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _schedule_reindex(self) -> None:
        """Schedule a re-index after the debounce window."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                _DEBOUNCE_SECONDS,
                self._enqueue,
            )
            self._timer.daemon = True
            self._timer.start()

    def _enqueue(self) -> None:
        """Put a re-index request on the worker queue."""
        logger.info("Watcher: queueing re-index for %s", self.project)
        self._queue.put(_IndexRequest(self.project, self.project_id, self.root))

    def _is_relevant(self, path: str) -> bool:
        """Check if the event path is a supported source file."""
        return Path(path).suffix in self._extensions

    def on_created(self, event: Any) -> None:
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule_reindex()

    def on_modified(self, event: Any) -> None:
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule_reindex()

    def on_deleted(self, event: Any) -> None:
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule_reindex()

    def on_moved(self, event: Any) -> None:
        if not event.is_directory:
            if self._is_relevant(event.src_path) or self._is_relevant(event.dest_path):
                self._schedule_reindex()


class CodeWatcher:
    """Watch directories for changes and trigger incremental code re-indexing.

    Usage:
        watcher = CodeWatcher(parser, graph_provider)
        watcher.watch("myproject", project_id=1, root=Path("/data/code/myproject"))
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(self, parser: Any, graph: Any) -> None:
        from cairn.code.indexer import CodeIndexer

        self._indexer = CodeIndexer(parser, graph)
        self._observer = Observer()
        self._observer.daemon = True
        self._queue: Queue[_IndexRequest] = Queue()
        self._watches: dict[str, Any] = {}  # project -> watch handle
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Cache supported extensions once
        from cairn.code.languages import supported_extensions
        self._extensions = frozenset(supported_extensions())

    def watch(self, project: str, project_id: int, root: Path) -> dict:
        """Start watching a directory for a project."""
        key = str(root)
        if key in self._watches:
            return {"message": f"Already watching: {key}"}

        handler = _ProjectEventHandler(
            project=project,
            project_id=project_id,
            root=root,
            queue=self._queue,
            supported_extensions=self._extensions,
        )
        watch = self._observer.schedule(handler, key, recursive=True)
        self._watches[key] = watch
        logger.info("Watcher: now monitoring %s for project %s", key, project)
        return {"message": f"Watching {key} for project {project}"}

    def unwatch(self, root: Path) -> dict:
        """Stop watching a directory."""
        key = str(root)
        watch = self._watches.pop(key, None)
        if not watch:
            return {"error": f"Not watching: {key}"}
        self._observer.unschedule(watch)
        logger.info("Watcher: stopped monitoring %s", key)
        return {"message": f"Stopped watching {key}"}

    def list_watched(self) -> list[str]:
        """Return list of currently watched paths."""
        return list(self._watches.keys())

    def start(self) -> None:
        """Start the observer and worker threads."""
        if self._observer.is_alive():
            return
        self._stop_event.clear()
        self._observer.start()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="code-watcher-worker")
        self._worker.start()
        logger.info("Code watcher started")

    def stop(self) -> None:
        """Stop the observer and worker threads."""
        self._stop_event.set()
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        logger.info("Code watcher stopped")

    def _worker_loop(self) -> None:
        """Process re-index requests from the queue sequentially."""
        while not self._stop_event.is_set():
            try:
                req = self._queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                logger.info("Watcher: re-indexing %s at %s", req.project, req.root)
                result = self._indexer.index_directory(
                    root=req.root,
                    project=req.project,
                    project_id=req.project_id,
                )
                logger.info("Watcher: %s — %s", req.project, result.summary())
            except Exception:
                logger.exception("Watcher: re-index failed for %s", req.project)
