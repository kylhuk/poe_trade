import os
import tempfile
import unittest
from unittest import mock

from poe_trade.config.settings import Settings
from poe_trade.db.clickhouse import ClickHouseClient


class SettingsAliasesTests(unittest.TestCase):
    def test_clickhouse_url_alias_from_ch_host(self):
        env = {
            "CH_HOST": "clickhouse.internal",
            "CH_PORT": "9001",
            "CH_SCHEME": "http",
            "POE_CLICKHOUSE_URL": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            settings = Settings.from_env()
        self.assertEqual(settings.clickhouse_url, "http://clickhouse.internal:9001")

    def test_cursor_dir_alias(self):
        env = {
            "POE_CHECKPOINT_DIR": "",
            "POE_CURSOR_DIR": "/tmp/poe-cursors",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            settings = Settings.from_env()
        self.assertEqual(settings.checkpoint_dir, "/tmp/poe-cursors")

    def test_neoplanus_runtime_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.ingest_contract_version, 2)
        self.assertTrue(settings.enable_psapi)
        self.assertFalse(settings.enable_cxapi)
        self.assertEqual(settings.psapi_poll_seconds, 30.0)
        self.assertEqual(settings.cxapi_backfill_hours, 168)
        self.assertEqual(settings.cxapi_hour_offset_seconds, 15)
        self.assertEqual(settings.refresh_refs_minutes, 5)
        self.assertEqual(settings.scan_minutes, 5)
        self.assertEqual(settings.raw_psapi_ttl_days, 21)
        self.assertEqual(settings.raw_cx_ttl_days, 365)
        self.assertEqual(settings.silver_ttl_days, 90)

    def test_psapi_poll_seconds_falls_back_to_market_poll_interval(self):
        env = {
            "POE_MARKET_POLL_INTERVAL": "12",
            "POE_PSAPI_POLL_SECONDS": "",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.psapi_poll_seconds, 12.0)

    def test_neoplanus_runtime_overrides(self):
        env = {
            "POE_ENABLE_PSAPI": "false",
            "POE_ENABLE_CXAPI": "true",
            "POE_PSAPI_POLL_SECONDS": "45",
            "POE_CXAPI_BACKFILL_HOURS": "24",
            "POE_CXAPI_HOUR_OFFSET_SECONDS": "30",
            "POE_REFRESH_REFS_MINUTES": "10",
            "POE_SCAN_MINUTES": "15",
            "POE_RAW_PSAPI_TTL_DAYS": "14",
            "POE_RAW_CX_TTL_DAYS": "180",
            "POE_SILVER_TTL_DAYS": "60",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.enable_psapi)
        self.assertTrue(settings.enable_cxapi)
        self.assertEqual(settings.psapi_poll_seconds, 45.0)
        self.assertEqual(settings.cxapi_backfill_hours, 24)
        self.assertEqual(settings.cxapi_hour_offset_seconds, 30)
        self.assertEqual(settings.refresh_refs_minutes, 10)
        self.assertEqual(settings.scan_minutes, 15)
        self.assertEqual(settings.raw_psapi_ttl_days, 14)
        self.assertEqual(settings.raw_cx_ttl_days, 180)
        self.assertEqual(settings.silver_ttl_days, 60)

    def test_clickhouse_client_aliases(self):
        env = {
            "CH_USER": "writer",
            "CH_PASSWORD": "secret",
            "CH_DATABASE": "ledger",
            "CH_TIMEOUT": "12",
            "POE_CLICKHOUSE_USER": "",
            "POE_CLICKHOUSE_PASSWORD": "",
            "POE_CLICKHOUSE_DATABASE": "",
            "POE_CLICKHOUSE_TIMEOUT": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            client = ClickHouseClient.from_env(endpoint="http://localhost:8123")
        self.assertEqual(client.user, "writer")
        self.assertEqual(client.password, "secret")
        self.assertEqual(client.database, "ledger")
        self.assertEqual(client.timeout, 12.0)

    def test_oauth_secret_file_overrides_env_secret(self):
        tmp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        try:
            tmp_file.write(" file-secret ")
            tmp_file.flush()
            env = {
                "POE_OAUTH_CLIENT_SECRET_FILE": tmp_file.name,
                "POE_OAUTH_CLIENT_SECRET": "ignored",
            }
            with mock.patch.dict(os.environ, env, clear=True):
                settings = Settings.from_env()
            self.assertEqual(settings.oauth_client_secret, "file-secret")
        finally:
            tmp_file.close()
            os.remove(tmp_file.name)

    def test_oauth_secret_file_missing_falls_back_to_env(self):
        env = {
            "POE_OAUTH_CLIENT_SECRET_FILE": "/does/not/exist",
            "POE_OAUTH_CLIENT_SECRET": "env-secret",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.oauth_client_secret, "env-secret")

    def test_oauth_secret_file_missing_without_env_is_empty(self):
        env = {
            "POE_OAUTH_CLIENT_SECRET_FILE": "/does/not/exist",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.oauth_client_secret, "")

    def test_stash_bootstrap_env_defaults(self):
        env = {
            "POE_STASH_BOOTSTRAP_UNTIL_LEAGUE": " Keepers ",
            "POE_STASH_BOOTSTRAP_FROM_BEGINNING": "true",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.stash_bootstrap_until_league, "Keepers")
        self.assertTrue(settings.stash_bootstrap_from_beginning)

    def test_invalid_stash_bootstrap_boolean_falls_back_to_default(self):
        env = {
            "POE_STASH_BOOTSTRAP_FROM_BEGINNING": "kinda",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.stash_bootstrap_from_beginning)


if __name__ == "__main__":
    unittest.main()
