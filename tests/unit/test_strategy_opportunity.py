import importlib


def test_expected_profit_per_operation_prefers_direct_trade() -> None:
    opportunity = importlib.import_module("poe_trade.strategy.opportunity")

    direct_trade = opportunity.OpportunityScoreInput(
        expected_profit_chaos=20.0,
        estimated_operations=1,
        estimated_whispers=1,
    )
    cumbersome_trade = opportunity.OpportunityScoreInput(
        expected_profit_chaos=30.0,
        estimated_operations=5,
        estimated_whispers=4,
    )

    assert opportunity.expected_profit_per_operation_chaos(
        direct_trade
    ) > opportunity.expected_profit_per_operation_chaos(cumbersome_trade)


def test_expected_profit_per_operation_returns_none_for_invalid_operations() -> None:
    opportunity = importlib.import_module("poe_trade.strategy.opportunity")

    snapshot = opportunity.OpportunityScoreInput(
        expected_profit_chaos=12.0,
        estimated_operations=0,
    )

    assert opportunity.expected_profit_per_operation_chaos(snapshot) is None


def test_expected_profit_per_operation_returns_none_without_profit() -> None:
    opportunity = importlib.import_module("poe_trade.strategy.opportunity")

    snapshot = opportunity.OpportunityScoreInput(
        expected_profit_chaos=None,
        estimated_operations=2,
    )

    assert opportunity.expected_profit_per_operation_chaos(snapshot) is None


def test_normalize_opportunity_metrics_uses_safe_defaults_for_sparse_rows() -> None:
    opportunity = importlib.import_module("poe_trade.strategy.opportunity")

    snapshot = opportunity.OpportunityScoreInput(
        expected_profit_chaos=84.0,
        estimated_operations=None,
        estimated_whispers=None,
        expected_profit_per_operation_chaos=None,
    )

    normalized = opportunity.normalize_opportunity_metrics(
        snapshot,
        default_estimated_operations=5,
        default_estimated_whispers=9,
        default_profit_per_operation_chaos=14.0,
    )

    assert normalized.estimated_operations == 5
    assert normalized.estimated_whispers == 9
    assert normalized.expected_profit_per_operation_chaos == 14.0
