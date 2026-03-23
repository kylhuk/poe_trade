FROM python:3.12-slim

WORKDIR /app

COPY requirements-runtime.txt ./

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements-runtime.txt

COPY pyproject.toml ./
COPY README.md ./
COPY poe_trade ./poe_trade

RUN pip install --no-cache-dir --no-deps .

COPY schema ./schema
COPY scripts ./scripts

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["poe-ledger-cli"]
