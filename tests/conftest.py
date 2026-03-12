"""Shared fixtures for the cairn test suite."""

import pytest

from cairn.core import stats
from cairn.core.trace import clear_trace


@pytest.fixture(autouse=True)
def _isolate_globals():
    """Reset module-level singletons between tests.

    Prevents cross-test contamination when integration tests (which use a real
    Postgres + EventBus) run before unit tests that use mocked services.
    """
    yield
    # Reset event bus reference so in_thread's finally block doesn't try
    # to emit into a disconnected database from a previous test.
    stats.init_event_bus_ref(None)
    clear_trace()
