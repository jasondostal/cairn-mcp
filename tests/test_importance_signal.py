"""Test importance signal in RRF search ranking."""


def rrf_score(rank: int, weight: float, k: int = 60) -> float:
    """RRF score component for a single signal."""
    return weight * (1.0 / (k + rank))


def test_importance_rank1_beats_rank50():
    """A rank-1 importance memory gets a higher contribution than rank-50."""
    weight = 0.08
    assert rrf_score(1, weight) > rrf_score(50, weight)


def test_importance_contribution_meaningful():
    """The importance signal contributes meaningfully to total score."""
    # Typical total RRF score range is 0.005-0.015
    # importance rank-1 contribution should be at least 0.001
    assert rrf_score(1, 0.08) > 0.001


def test_importance_does_not_dominate_vector():
    """importance at 8% should not outweigh vector at 46%."""
    importance_best = rrf_score(1, 0.08)
    vector_worst = rrf_score(50, 0.46)
    assert vector_worst > importance_best


def test_all_weight_configs_sum_to_one():
    """Verify rebalanced weight configs sum to 1.0."""
    from cairn.core.constants import (
        RRF_WEIGHTS_DEFAULT,
        RRF_WEIGHTS_WITH_ACCESS,
        RRF_WEIGHTS_WITH_ACCESS_ENTITIES,
        RRF_WEIGHTS_WITH_ACTIVATION,
        RRF_WEIGHTS_WITH_ENTITIES,
        RRF_WEIGHTS_WITH_GRAPH,
    )

    for name, weights in [
        ("default", RRF_WEIGHTS_DEFAULT),
        ("entities", RRF_WEIGHTS_WITH_ENTITIES),
        ("activation", RRF_WEIGHTS_WITH_ACTIVATION),
        ("graph", RRF_WEIGHTS_WITH_GRAPH),
        ("access", RRF_WEIGHTS_WITH_ACCESS),
        ("access_entities", RRF_WEIGHTS_WITH_ACCESS_ENTITIES),
    ]:
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"{name} weights sum to {total}, expected 1.0"


def test_importance_key_in_all_weight_configs():
    """importance must be present in ALL weight configs."""
    from cairn.core.constants import (
        RRF_WEIGHTS_DEFAULT,
        RRF_WEIGHTS_WITH_ACCESS,
        RRF_WEIGHTS_WITH_ACCESS_ENTITIES,
        RRF_WEIGHTS_WITH_ACTIVATION,
        RRF_WEIGHTS_WITH_ENTITIES,
        RRF_WEIGHTS_WITH_GRAPH,
    )

    for name, weights in [
        ("default", RRF_WEIGHTS_DEFAULT),
        ("entities", RRF_WEIGHTS_WITH_ENTITIES),
        ("activation", RRF_WEIGHTS_WITH_ACTIVATION),
        ("graph", RRF_WEIGHTS_WITH_GRAPH),
        ("access", RRF_WEIGHTS_WITH_ACCESS),
        ("access_entities", RRF_WEIGHTS_WITH_ACCESS_ENTITIES),
    ]:
        assert "importance" in weights, f"{name} missing 'importance' key"
