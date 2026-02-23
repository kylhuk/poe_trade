import tempfile
import unittest

from poe_trade.ingestion.checkpoints import CheckpointStore


class CheckpointStoreTests(unittest.TestCase):
    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(tmp)
            store.write("key-1", "value")
            self.assertEqual(store.read("key-1"), "value")
            store.write("key-1", "updated")
            self.assertEqual(store.read("key-1"), "updated")
            store.delete("key-1")
            self.assertIsNone(store.read("key-1"))


if __name__ == "__main__":
    unittest.main()
