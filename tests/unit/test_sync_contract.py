import pytest

from poe_trade.config import constants
from poe_trade.ingestion.sync_contract import is_supported_feed_kind, queue_key


def test_queue_key_for_psapi() -> None:
    assert queue_key(constants.FEED_KIND_PSAPI, "PC") == "psapi:pc"


def test_queue_key_for_cxapi() -> None:
    assert queue_key(constants.FEED_KIND_CXAPI, "xbox") == "cxapi:xbox"


def test_queue_key_rejects_unknown_feed_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported feed kind"):
        queue_key("unknown", "pc")


def test_queue_key_rejects_empty_realm() -> None:
    with pytest.raises(ValueError, match="Realm must be non-empty"):
        queue_key(constants.FEED_KIND_PSAPI, "   ")


def test_supported_feed_kinds() -> None:
    assert is_supported_feed_kind(constants.FEED_KIND_PSAPI)
    assert is_supported_feed_kind(constants.FEED_KIND_CXAPI)
    assert is_supported_feed_kind(constants.FEED_KIND_ACCOUNT_STASH)
    assert not is_supported_feed_kind("legacy")
