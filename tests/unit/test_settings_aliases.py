import os
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

    def test_clickhouse_client_aliases(self):
        env = {
            "CH_USER": "writer",
            "CH_PASSWORD": "secret",
            "CH_DATABASE": "ledger",
            "CH_TIMEOUT": "12",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            client = ClickHouseClient.from_env(endpoint="http://localhost:8123")
        self.assertEqual(client.user, "writer")
        self.assertEqual(client.password, "secret")
        self.assertEqual(client.database, "ledger")
        self.assertEqual(client.timeout, 12.0)


if __name__ == "__main__":
    unittest.main()
