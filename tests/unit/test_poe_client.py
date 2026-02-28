import io
import http.client
import urllib.error
import urllib.request

from poe_trade.ingestion.poe_client import PoeClient
from poe_trade.ingestion.rate_limit import RateLimitPolicy


def _make_response(body, headers):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return body

        def getheaders(self):
            return list(headers.items())

        def getcode(self):
            return 200

    return _Resp()


def test_request_retries_on_429(monkeypatch):
    policy = RateLimitPolicy(
        max_retries=1, backoff_base=0.1, backoff_max=1.0, jitter=0.0
    )
    client = PoeClient("https://poe.com", policy, user_agent="agent", timeout=1.0)
    sleep_calls: list[float] = []
    attempts = {"count": 0}

    def fake_sleep(duration):
        sleep_calls.append(duration)

    def fake_urlopen(req, timeout):
        if attempts["count"] == 0:
            attempts["count"] += 1
            headers = http.client.HTTPMessage()
            headers.add_header("Retry-After", "0.2")
            raise urllib.error.HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(b'{"error": "limit"}'),
            )
        return _make_response(b'{"ok": true}', {"Content-Type": "application/json"})

    monkeypatch.setattr("poe_trade.ingestion.poe_client.time.sleep", fake_sleep)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    response = client.request("GET", "public-stash-tabs")

    assert response == {"ok": True}
    assert sleep_calls == [0.2]
    assert attempts["count"] == 1


def test_request_retries_on_url_error(monkeypatch):
    policy = RateLimitPolicy(
        max_retries=1, backoff_base=0.3, backoff_max=1.0, jitter=0.0
    )
    client = PoeClient("https://poe.com", policy, user_agent="agent", timeout=1.0)
    sleep_calls: list[float] = []
    attempts = {"count": 0}

    def fake_sleep(duration):
        sleep_calls.append(duration)

    def fake_urlopen(req, timeout):
        if attempts["count"] == 0:
            attempts["count"] += 1
            raise urllib.error.URLError("temporary failure")
        return _make_response(b'{"value": 1}', {"Content-Type": "application/json"})

    monkeypatch.setattr("poe_trade.ingestion.poe_client.time.sleep", fake_sleep)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    response = client.request("GET", "public-stash-tabs")

    assert response == {"value": 1}
    assert sleep_calls == [0.3]
    assert attempts["count"] == 1


def test_request_applies_dynamic_rate_limit_pacing(monkeypatch):
    policy = RateLimitPolicy(
        max_retries=0, backoff_base=0.1, backoff_max=1.0, jitter=0.0
    )
    client = PoeClient("https://poe.com", policy, user_agent="agent", timeout=1.0)
    sleep_calls: list[float] = []
    responses = [
        _make_response(
            b'{"ok": true}',
            {
                "Content-Type": "application/json",
                "X-Rate-Limit-Rules": "client",
                "X-Rate-Limit-Client": "10:5:10",
                "X-Rate-Limit-Client-State": "1:5:0",
            },
        ),
        _make_response(b'{"ok": true}', {"Content-Type": "application/json"}),
    ]

    def fake_sleep(duration):
        sleep_calls.append(duration)

    def fake_urlopen(req, timeout):
        return responses.pop(0)

    monkeypatch.setattr("poe_trade.ingestion.poe_client.time.sleep", fake_sleep)
    monkeypatch.setattr("poe_trade.ingestion.rate_limit.time.monotonic", lambda: 0.0)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    first = client.request("GET", "public-stash-tabs")
    second = client.request("GET", "public-stash-tabs")

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert sleep_calls == [0.5]



def test_request_with_metadata_exposes_headers(monkeypatch):
    policy = RateLimitPolicy(
        max_retries=0, backoff_base=0.1, backoff_max=1.0, jitter=0.0
    )
    client = PoeClient(
        "https://poe.com", policy, user_agent="agent", timeout=1.0
    )

    def fake_urlopen(req, timeout):
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true}'

            def getheaders(self):
                return [("X-Rate-Limit-Test", "value")]

            def getcode(self):
                return 200

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    response = client.request_with_metadata("GET", "public-stash-tabs")

    assert response.payload == {"ok": True}
    assert response.headers["X-Rate-Limit-Test"] == "value"
    assert response.status_code == 200
    assert response.attempts == 1
    assert response.duration_ms >= 0

