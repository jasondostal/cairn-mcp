"""Test decay scoring math."""

import math


def decay_score(days_since_access: float, lambda_: float = 0.01) -> float:
    """Pure decay function matching the SQL: EXP(-lambda * days)."""
    return math.exp(-lambda_ * days_since_access)


def test_recent_memory_scores_high():
    assert decay_score(0) == 1.0


def test_old_untouched_memory_scores_low():
    assert decay_score(250) < 0.1


def test_half_life():
    half_life = math.log(2) / 0.01  # ~69.3 days
    score = decay_score(half_life)
    assert abs(score - 0.5) < 0.01


def test_accessed_memory_beats_unaccessed():
    """A memory accessed yesterday beats one untouched for 60 days."""
    accessed = decay_score(1)
    stale = decay_score(60)
    assert accessed > stale


def test_lambda_controls_decay_rate():
    """Higher lambda = faster decay."""
    slow = decay_score(30, lambda_=0.005)
    fast = decay_score(30, lambda_=0.05)
    assert slow > fast


def test_one_week_still_high():
    """A week-old memory should still score well."""
    assert decay_score(7) > 0.9


def test_one_year_very_low():
    """A year-old untouched memory should be nearly forgotten."""
    assert decay_score(365) < 0.03
