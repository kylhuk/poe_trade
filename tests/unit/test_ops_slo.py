import unittest
from datetime import datetime, timedelta, timezone

from poe_trade.ops.slo import (
    detect_checkpoint_drift,
    detect_repeated_rate_errors,
    evaluate_ingest_freshness,
)


class OpsSLOHelpersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = datetime(2025, 2, 23, 12, 0, tzinfo=timezone.utc)

    def test_ingest_freshness_targets(self):
        public_last = self.reference - timedelta(minutes=5)
        currency_last = self.reference - timedelta(minutes=80)
        statuses = evaluate_ingest_freshness(public_last, currency_last, self.reference)
        self.assertEqual(len(statuses), 2)
        public, currency = statuses
        self.assertTrue(public.within_slo)
        self.assertFalse(currency.within_slo)
        self.assertIn("lag", currency.note)
        self.assertEqual(currency.target_minutes, 65)

    def test_checkpoint_drift_alert(self):
        burst = detect_checkpoint_drift(
            cursor_name="processing",
            last_checkpoint=self.reference - timedelta(minutes=22),
            reference=self.reference,
            expected_interval_minutes=10,
        )
        self.assertTrue(burst.alert)
        self.assertEqual(burst.cursor_name, "processing")
        self.assertGreaterEqual(burst.drift_minutes, 20)

    def test_repeated_rate_errors(self):
        errors = detect_repeated_rate_errors({429: 6, 404: 3, 418: 1}, window_minutes=30, threshold=5)
        critical = [entry for entry in errors if entry.status_code == 429][0]
        warning = [entry for entry in errors if entry.status_code == 404][0]
        self.assertTrue(critical.alert)
        self.assertFalse(warning.alert)
        self.assertEqual(warning.severity, "warning")
        self.assertEqual(critical.window_minutes, 30)
