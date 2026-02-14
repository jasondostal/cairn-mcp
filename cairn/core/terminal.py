"""Terminal host management — CRUD for SSH hosts used by the web terminal."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from cairn.config import TerminalConfig
from cairn.core.analytics import track_operation
from cairn.storage.database import Database

logger = logging.getLogger(__name__)


class TerminalHostManager:
    """Manages SSH host entries for the web terminal (native + ttyd modes)."""

    def __init__(self, db: Database, config: TerminalConfig):
        self.db = db
        self.config = config
        self.cipher = None
        if config.encryption_key:
            try:
                from cryptography.fernet import Fernet
                self.cipher = Fernet(config.encryption_key.encode())
            except Exception:
                logger.warning("Failed to initialize Fernet cipher — credential encryption unavailable")

    def _encrypt(self, plaintext: str) -> str:
        if not self.cipher:
            raise ValueError("Encryption key not configured")
        return self.cipher.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        if not self.cipher:
            raise ValueError("Encryption key not configured")
        return self.cipher.decrypt(ciphertext.encode()).decode()

    @track_operation("terminal.create")
    def create(
        self,
        name: str,
        hostname: str,
        port: int = 22,
        username: str | None = None,
        credential: str | None = None,
        auth_method: str = "password",
        ttyd_url: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create a new SSH host entry.

        For native mode: requires username + credential.
        For ttyd mode: requires ttyd_url.
        """
        backend = self.config.backend

        if backend == "native":
            if not username:
                raise ValueError("username is required for native backend")
            if not credential:
                raise ValueError("credential (password or key) is required for native backend")
            if auth_method not in ("password", "key"):
                raise ValueError(f"Invalid auth_method: {auth_method}. Must be 'password' or 'key'.")
        elif backend == "ttyd":
            if not ttyd_url:
                raise ValueError("ttyd_url is required for ttyd backend")

        encrypted_creds = None
        if credential and self.cipher:
            encrypted_creds = self._encrypt(credential)

        row = self.db.execute_one(
            """
            INSERT INTO ssh_hosts (name, hostname, port, username, auth_method,
                                   encrypted_creds, ttyd_url, description, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, name, created_at
            """,
            (
                name, hostname, port, username, auth_method,
                encrypted_creds, ttyd_url, description,
                json.dumps(metadata or {}),
            ),
        )
        self.db.commit()

        logger.info("Created SSH host '%s' (id=%d, backend=%s)", name, row["id"], backend)
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"].isoformat(),
        }

    @track_operation("terminal.list")
    def list(self, include_inactive: bool = False) -> dict:
        """List all SSH hosts. Never returns encrypted credentials."""
        where = "TRUE" if include_inactive else "is_active = true"

        rows = self.db.execute(
            f"""
            SELECT id, name, hostname, port, username, auth_method,
                   ttyd_url, description, is_active, metadata,
                   created_at, updated_at
            FROM ssh_hosts
            WHERE {where}
            ORDER BY name ASC
            """,
        )

        items = [
            {
                "id": r["id"],
                "name": r["name"],
                "hostname": r["hostname"],
                "port": r["port"],
                "username": r["username"],
                "auth_method": r["auth_method"],
                "ttyd_url": r["ttyd_url"],
                "description": r["description"],
                "is_active": r["is_active"],
                "metadata": r["metadata"] or {},
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

        return {"items": items}

    @track_operation("terminal.get")
    def get(self, host_id: int, decrypt: bool = False) -> dict | None:
        """Get a single host by ID. Set decrypt=True to include decrypted credentials (native mode)."""
        row = self.db.execute_one(
            """
            SELECT id, name, hostname, port, username, auth_method,
                   encrypted_creds, ttyd_url, description, is_active, metadata,
                   created_at, updated_at
            FROM ssh_hosts WHERE id = %s
            """,
            (host_id,),
        )
        if not row:
            return None

        result = {
            "id": row["id"],
            "name": row["name"],
            "hostname": row["hostname"],
            "port": row["port"],
            "username": row["username"],
            "auth_method": row["auth_method"],
            "ttyd_url": row["ttyd_url"],
            "description": row["description"],
            "is_active": row["is_active"],
            "metadata": row["metadata"] or {},
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

        if decrypt and row["encrypted_creds"] and self.cipher:
            try:
                result["credential"] = self._decrypt(row["encrypted_creds"])
            except Exception:
                logger.warning("Failed to decrypt credentials for host %d", host_id)
                result["credential"] = None
        return result

    @track_operation("terminal.update")
    def update(self, host_id: int, **fields) -> dict:
        """Update host fields. Supports: name, hostname, port, username, credential,
        auth_method, ttyd_url, description, is_active, metadata."""
        allowed = {
            "name", "hostname", "port", "username", "auth_method",
            "ttyd_url", "description", "is_active", "metadata",
        }

        sets = ["updated_at = NOW()"]
        params: list = []

        # Handle credential specially — encrypt before storing
        if "credential" in fields:
            cred = fields.pop("credential")
            if cred is not None and self.cipher:
                sets.append("encrypted_creds = %s")
                params.append(self._encrypt(cred))
            elif cred is None:
                sets.append("encrypted_creds = NULL")

        for key, val in fields.items():
            if key not in allowed:
                continue
            if key == "metadata":
                sets.append("metadata = %s::jsonb")
                params.append(json.dumps(val or {}))
            else:
                sets.append(f"{key} = %s")
                params.append(val)

        if len(sets) == 1:  # only updated_at
            return {"updated": True, "id": host_id}

        params.append(host_id)
        self.db.execute(
            f"UPDATE ssh_hosts SET {', '.join(sets)} WHERE id = %s",
            tuple(params),
        )
        self.db.commit()

        logger.info("Updated SSH host %d", host_id)
        return {"updated": True, "id": host_id}

    @track_operation("terminal.delete")
    def delete(self, host_id: int) -> dict:
        """Soft-delete a host (set is_active = false)."""
        self.db.execute(
            "UPDATE ssh_hosts SET is_active = false, updated_at = NOW() WHERE id = %s",
            (host_id,),
        )
        self.db.commit()

        logger.info("Soft-deleted SSH host %d", host_id)
        return {"deleted": True, "id": host_id}
