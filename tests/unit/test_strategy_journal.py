import importlib


class _RecordingClient:
    def __init__(self):
        self.queries = []

    def execute(self, query: str) -> str:
        self.queries.append(query)
        return ""


def test_record_trade_event_writes_event_and_position() -> None:
    journal = importlib.import_module("poe_trade.strategy.journal")
    client = _RecordingClient()

    event_id = journal.record_trade_event(
        client,
        action="buy",
        strategy_id="bulk_essence",
        league="Mirage",
        item_or_market_key="essence-key",
        price_chaos=100,
        quantity=20,
        notes="entry",
        dry_run=False,
    )

    assert len(event_id) == 32
    assert len(client.queries) == 2
    assert "journal_events" in client.queries[0]
    assert "journal_positions" in client.queries[1]


def test_record_trade_event_dry_run_skips_clickhouse() -> None:
    journal = importlib.import_module("poe_trade.strategy.journal")
    client = _RecordingClient()

    event_id = journal.record_trade_event(
        client,
        action="sell",
        strategy_id="bulk_essence",
        league="Mirage",
        item_or_market_key="essence-key",
        price_chaos=120,
        quantity=10,
        dry_run=True,
    )

    assert len(event_id) == 32
    assert client.queries == []
