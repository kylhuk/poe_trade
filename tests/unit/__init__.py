import sys
import types
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
poe_trade_dir = project_root / "poe_trade"

if "poe_trade" not in sys.modules:
    poe_trade_stub = types.ModuleType("poe_trade")
    poe_trade_stub.__path__ = [str(poe_trade_dir)]
    sys.modules["poe_trade"] = poe_trade_stub

try:
    import fastapi  # type: ignore[import]
except ImportError:  # pragma: no cover - availability varies
    class FastAPIStub:
        def __init__(self, **kwargs):
            self._routes = []

        def get(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def post(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    def Header(default=None, **kwargs):  # type: ignore[no-untyped-def]
        return default

    status = types.SimpleNamespace(
        HTTP_503_SERVICE_UNAVAILABLE=503,
        HTTP_401_UNAUTHORIZED=401,
    )

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = FastAPIStub
    fastapi.HTTPException = Exception
    fastapi.Header = Header
    fastapi.status = status

    testclient_module = types.ModuleType("fastapi.testclient")

    class TestClientStub:
        def __init__(self, app, *_, **__):
            self.app = app

    testclient_module.TestClient = TestClientStub
    fastapi.testclient = testclient_module
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.testclient"] = testclient_module

try:
    import httpx  # type: ignore[import]
except ImportError:  # pragma: no cover - availability varies
    class HTTPStatusError(Exception):
        def __init__(self, message, response=None):
            super().__init__(message)
            self.response = response

    class Client:
        def __init__(self, *args, **kwargs):
            self.closed = False

        def request(self, *args, **kwargs):
            class Response:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {}

            return Response()

        def close(self):
            self.closed = True

    httpx = types.ModuleType("httpx")
    httpx.Client = Client
    httpx.HTTPStatusError = HTTPStatusError
    sys.modules["httpx"] = httpx
