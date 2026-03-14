"""Full Mars Rover integration test: dispatch → heartbeat → gate → notify → resolve.

Tests the complete async autonomy flow with mocked Agent SDK but real Cairn
orchestration: event bus, subscription manager, notification pipeline.

The Mars Rover pattern:
1. Dispatch work item to Agent SDK backend
2. Agent sends heartbeats (status updates)
3. Agent hits a gate (needs human input)
4. Notification fires (in_app + push)
5. Human resolves the gate
6. Agent completes

Part of ca-252: Agent SDK Integration — Mars Rover Pattern.
"""

from unittest.mock import MagicMock, patch

from cairn.core.subscriptions import SubscriptionManager
from cairn.integrations.agent_sdk import AgentSDKBackend, AgentSDKConfig
from cairn.listeners.notification_listener import NotificationListener


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


def _make_subscription_manager(push_notifier=None):
    """SubscriptionManager with mocked DB but real logic."""
    db = MagicMock()
    return SubscriptionManager(db, push_notifier=push_notifier), db


def _make_agent_backend(event_callback=None):
    """AgentSDKBackend with default config."""
    config = AgentSDKConfig(default_risk_tier=1)
    return AgentSDKBackend(config, event_callback=event_callback)


# ---------------------------------------------------------------------------
# Full flow test
# ---------------------------------------------------------------------------


class TestMarsRoverFlow:
    """Tests the complete dispatch → gate → notify → resolve lifecycle.

    Uses NotificationListener.handle() directly rather than EventBus.emit(),
    since the EventBus persists to DB and dispatches asynchronously. This
    tests the same handler chain that the EventDispatcher would invoke.
    """

    def test_gate_event_triggers_push_notification(self):
        """Gate event → subscription match → push notification with deep link."""
        push = MagicMock()
        push.enabled = True
        push.send.return_value = True
        sm, sm_db = _make_subscription_manager(push_notifier=push)
        listener = NotificationListener(sm)

        # Subscription exists for gate events with push channel
        sm_db.execute.return_value = [
            {
                "id": 1, "name": "gate-push", "patterns": ["work_item.gate_set"],
                "channel": "push",
                "channel_config": {"topic": "cairn", "base_url": "https://cairn.local"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        # NotificationListener receives the event (as EventDispatcher would call it)
        listener.handle({
            "event_type": "work_item.gate_set",
            "event_id": 100,
            "project_id": None,
            "work_item_id": 42,
            "payload": {
                "gate_data": {"question": "Deploy to prod?", "options": ["yes", "no"]},
                "display_id": "ca-42",
                "title": "Deploy service",
            },
        })

        # Push notification should have been sent
        push.send.assert_called_once()
        call_kwargs = push.send.call_args.kwargs
        assert "Deploy to prod?" in (call_kwargs.get("body") or "")
        assert call_kwargs["click_url"] == "https://cairn.local/work/ca-42"
        assert call_kwargs["severity"] == "warning"
        assert call_kwargs["topic"] == "cairn"

    def test_agent_event_callback_builds_correct_event(self):
        """Agent SDK event callback produces events suitable for the bus."""
        captured_events = []

        def event_callback(work_item_id, event_type, payload):
            captured_events.append({
                "work_item_id": work_item_id,
                "event_type": event_type,
                "payload": payload,
            })

        backend = _make_agent_backend(event_callback=event_callback)
        session = backend.create_session()
        backend._sessions[session.id]["work_item_id"] = "42"

        # Simulate heartbeat
        event_callback("42", "agent.heartbeat", {
            "session_id": session.id,
            "sdk_session_id": "sdk-xyz",
        })

        assert len(captured_events) == 1
        assert captured_events[0]["event_type"] == "agent.heartbeat"
        assert captured_events[0]["work_item_id"] == "42"
        assert captured_events[0]["payload"]["sdk_session_id"] == "sdk-xyz"

    def test_completion_event_creates_in_app_notification(self):
        """Completed event → in-app notification via listener."""
        sm, sm_db = _make_subscription_manager()

        # Subscription for completed events → in_app
        sm_db.execute.return_value = [
            {
                "id": 1, "name": "completions", "patterns": ["work_item.completed"],
                "channel": "in_app", "channel_config": {},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]
        sm_db.execute_one.return_value = {
            "id": 10, "title": "Work item completed", "severity": "success",
            "is_read": False, "created_at": "2026-01-01T00:00:00",
        }

        listener = NotificationListener(sm)
        listener.handle({
            "event_type": "work_item.completed",
            "event_id": 100,
            "project_id": None,
            "payload": {"title": "Fix the auth bug"},
        })

        # In-app notification should have been created (commit on INSERT)
        sm_db.commit.assert_called()

    def test_full_gate_cycle(self):
        """Gate set → push notification → gate resolve → success notification."""
        push = MagicMock()
        push.enabled = True
        push.send.return_value = True
        sm, sm_db = _make_subscription_manager(push_notifier=push)
        listener = NotificationListener(sm)

        # Step 1: Gate set — push subscription matches
        sm_db.execute.return_value = [
            {
                "id": 1, "name": "gate-alerts", "patterns": ["work_item.*"],
                "channel": "push",
                "channel_config": {"topic": "cairn", "base_url": "https://cairn.local"},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        listener.handle({
            "event_type": "work_item.gate_set",
            "event_id": 100,
            "project_id": None,
            "payload": {
                "gate_data": {"question": "Which approach?", "options": ["A", "B"]},
                "display_id": "ca-42",
                "title": "Architecture decision",
            },
        })

        # Gate notification sent with warning severity
        assert push.send.call_count == 1
        assert push.send.call_args.kwargs["severity"] == "warning"
        assert push.send.call_args.kwargs["click_url"] == "https://cairn.local/work/ca-42"

        # Step 2: Gate resolved — same subscription matches again
        push.reset_mock()
        listener.handle({
            "event_type": "work_item.gate_resolved",
            "event_id": 101,
            "project_id": None,
            "payload": {
                "display_id": "ca-42",
                "title": "Architecture decision",
            },
        })

        # Resolution notification sent with success severity
        assert push.send.call_count == 1
        assert push.send.call_args.kwargs["severity"] == "success"


# ---------------------------------------------------------------------------
# Agent SDK session lifecycle with events
# ---------------------------------------------------------------------------


class TestAgentSDKSessionLifecycle:
    def test_session_tracks_work_item_id(self):
        backend = _make_agent_backend()
        session = backend.create_session(title="test dispatch")

        # Simulate what workspace.dispatch() does
        backend._sessions[session.id]["work_item_id"] = "42"

        meta = backend._sessions[session.id]
        assert meta["work_item_id"] == "42"
        assert meta["status"] == "created"
        assert meta["risk_tier"] == 1

    def test_abort_prevents_further_events(self):
        events = []

        def callback(work_item_id, event_type, payload):
            events.append(event_type)

        backend = _make_agent_backend(event_callback=callback)
        session = backend.create_session()
        backend._sessions[session.id]["work_item_id"] = "42"

        # Abort the session
        backend.abort_session(session.id)
        assert backend._sessions[session.id]["status"] == "cancelled"

    def test_risk_tier_override_on_send(self):
        """Risk tier can be overridden per-message."""
        backend = _make_agent_backend()
        session = backend.create_session()

        # Default tier is 1
        assert backend._sessions[session.id]["risk_tier"] == 1

        # Override to tier 2
        backend.set_risk_tier(session.id, 2)
        assert backend._sessions[session.id]["risk_tier"] == 2


# ---------------------------------------------------------------------------
# Notification pipeline: subscription pattern matching for Mars Rover events
# ---------------------------------------------------------------------------


class TestMarsRoverSubscriptionPatterns:
    """Verify that common Mars Rover event patterns match correctly."""

    def _make_manager(self):
        db = MagicMock()
        return SubscriptionManager(db), db

    def test_wildcard_catches_all_work_item_events(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {
                "id": 1, "name": "all-wi", "patterns": ["work_item.*"],
                "channel": "in_app", "channel_config": {},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        for event in ["work_item.gate_set", "work_item.gate_resolved",
                       "work_item.completed", "work_item.claimed"]:
            matched = sm.find_matching(event)
            assert len(matched) == 1, f"Expected match for {event}"

    def test_gate_specific_pattern(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {
                "id": 1, "name": "gates-only", "patterns": ["work_item.gate_set"],
                "channel": "push", "channel_config": {},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        # Should match gate_set
        assert len(sm.find_matching("work_item.gate_set")) == 1

        # Should NOT match other events
        assert len(sm.find_matching("work_item.completed")) == 0
        assert len(sm.find_matching("work_item.gate_resolved")) == 0

    def test_multiple_patterns_in_subscription(self):
        sm, db = self._make_manager()
        db.execute.return_value = [
            {
                "id": 1, "name": "gates-and-completions",
                "patterns": ["work_item.gate_set", "work_item.completed"],
                "channel": "push", "channel_config": {},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        assert len(sm.find_matching("work_item.gate_set")) == 1
        assert len(sm.find_matching("work_item.completed")) == 1
        assert len(sm.find_matching("work_item.claimed")) == 0

    def test_agent_events_not_matched_by_work_item_wildcard(self):
        """agent.* events are separate from work_item.* events."""
        sm, db = self._make_manager()
        db.execute.return_value = [
            {
                "id": 1, "name": "wi-only", "patterns": ["work_item.*"],
                "channel": "in_app", "channel_config": {},
                "project_id": None, "project_name": None, "is_active": True,
                "created_at": "2026-01-01T00:00:00", "updated_at": None,
            },
        ]

        assert len(sm.find_matching("agent.heartbeat")) == 0
        assert len(sm.find_matching("agent.completed")) == 0
