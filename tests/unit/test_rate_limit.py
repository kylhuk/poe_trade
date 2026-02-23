import unittest
from unittest.mock import patch

from poe_trade.ingestion.rate_limit import RateLimitPolicy, parse_retry_after


class RateLimitTests(unittest.TestCase):
    def test_parse_retry_after_seconds(self):
        self.assertEqual(parse_retry_after({"Retry-After": "5"}), 5.0)

    def test_parse_retry_after_date(self):
        parsed = parse_retry_after({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        self.assertIsNotNone(parsed)

    @patch("poe_trade.ingestion.rate_limit.random.uniform", return_value=0.1)
    def test_next_backoff_with_jitter(self, mock_uniform):
        policy = RateLimitPolicy(max_retries=2, backoff_base=1.0, backoff_max=4.0, jitter=0.5)
        delay = policy.next_backoff(1, {})
        expected = min(1.0 * 2, 4.0) + 0.1
        self.assertAlmostEqual(delay, expected)
        mock_uniform.assert_called_once()

    def test_next_backoff_prefers_retry_after(self):
        policy = RateLimitPolicy(max_retries=2, backoff_base=1.0, backoff_max=5.0, jitter=0.0)
        delay = policy.next_backoff(0, {"Retry-After": "3"})
        self.assertEqual(delay, 3.0)

    @patch("poe_trade.ingestion.rate_limit.random.uniform")
    def test_retry_after_not_capped_or_jittered(self, mock_uniform):
        policy = RateLimitPolicy(max_retries=2, backoff_base=1.0, backoff_max=5.0, jitter=0.5)
        delay = policy.next_backoff(0, {"Retry-After": "120"})
        self.assertEqual(delay, 120.0)
        mock_uniform.assert_not_called()
