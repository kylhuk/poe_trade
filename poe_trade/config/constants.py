"""Shared runtime constants for PoE ledger services."""

SERVICE_NAMES = [
    "market_harvester",
    "stash_scribe",
]
OPTIONAL_SERVICES = ["stash_scribe"]
DEFAULT_REALMS = ["pc"]
DEFAULT_LEAGUES = ["Synthesis"]
DEFAULT_TIME_BUCKETS = ["1h", "6h", "24h"]
DEFAULT_THRESHOLDS = {
    "min_listing_count": 5,
    "max_price_spread": 0.25,
    "session_profit_min": 0.1,
}
DEFAULT_CHAOS_CURRENCY = "chaos"
DEFAULT_CLICKHOUSE_URL = "http://clickhouse:8123"
DEFAULT_SERVICE_PORTS: dict[str, int] = {}


DEFAULT_POE_API_BASE_URL = "https://api.pathofexile.com"
DEFAULT_POE_AUTH_BASE_URL = "https://www.pathofexile.com/oauth"
DEFAULT_POE_USER_AGENT = "poe-trade/0.1"
DEFAULT_RATE_LIMIT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_BACKOFF_BASE = 1.0
DEFAULT_RATE_LIMIT_BACKOFF_MAX = 30.0
DEFAULT_RATE_LIMIT_JITTER = 0.5
DEFAULT_POE_REQUEST_TIMEOUT = 30.0
DEFAULT_CHECKPOINT_DIR = "/tmp/poe_trade/checkpoints"
DEFAULT_MARKET_POLL_INTERVAL = 10.0
DEFAULT_STASH_POLL_INTERVAL = 60.0
DEFAULT_STASH_TRIGGER_TOKEN = ""
DEFAULT_OAUTH_GRANT_TYPE = "client_credentials"
DEFAULT_OAUTH_SCOPE = "service:psapi"
DEFAULT_POE_STASH_API_PATH = "public-stash-tabs"
