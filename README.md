# Crypto Signal Bot — Steps 1 & 2

- **Step 1**: Repo & Config (`config/config.yaml`, `.env.example`, Docker, requirements).
- **Step 2**: WebSocket ingestion (Binance 1m) + Candle roll-up to M15/H1/H4/D1/W1 with on-close prints.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app              # banner
python -m app.ingest       # run WS + roll-up
```

## Docker
```bash
docker compose up --build
```

## Config
Edit `config/config.yaml` (symbols, market_type, timeframes, alerts...)
