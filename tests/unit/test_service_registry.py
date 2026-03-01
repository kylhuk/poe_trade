from poe_trade.config import constants


def test_ingestion_service_registry_names() -> None:
    assert constants.SERVICE_NAMES == ["market_harvester"]


def test_optional_service_registry_names() -> None:
    assert constants.OPTIONAL_SERVICES == []
