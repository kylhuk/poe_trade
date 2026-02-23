import sys
import types
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
poe_trade_dir = project_root / "poe_trade"

if "poe_trade" not in sys.modules:
    poe_trade_stub = types.ModuleType("poe_trade")
    poe_trade_stub.__path__ = [str(poe_trade_dir)]
    sys.modules["poe_trade"] = poe_trade_stub

if "fastapi" not in sys.modules:
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

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = FastAPIStub
    fastapi.HTTPException = Exception
    sys.modules["fastapi"] = fastapi

if "httpx" not in sys.modules:
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
