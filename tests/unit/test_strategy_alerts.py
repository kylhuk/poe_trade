import importlib


class _RecordingClient:
    def __init__(self, payload: str = ""):
        self.payload = payload
        self.queries = []

    def execute(self, query: str) -> str:
        self.queries.append(query)
        return self.payload


def test_list_alerts_parses_json_each_row() -> None:
    alerts = importlib.import_module("poe_trade.strategy.alerts")
    payload = '{"alert_id":"a1","strategy_id":"bulk_essence","league":"Mirage","item_or_market_key":"k1","status":"new","recorded_at":"2026-03-10 20:00:00.000"}'
    client = _RecordingClient(payload)

    rows = alerts.list_alerts(client)

    assert rows[0]["alert_id"] == "a1"
    assert "scanner_alert_log" in client.queries[0]


def test_ack_alert_inserts_ack_row() -> None:
    alerts = importlib.import_module("poe_trade.strategy.alerts")
    client = _RecordingClient()

    alert_id = alerts.ack_alert(client, alert_id="a1")

    assert alert_id == "a1"
    assert len(client.queries) == 1
    assert "acked" in client.queries[0]
