FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY poe_trade ./poe_trade

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

COPY . .

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["poe-ledger-cli"]
