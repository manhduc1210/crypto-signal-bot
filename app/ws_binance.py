import asyncio, json, websockets
from typing import List, AsyncIterator

def _stream_url(market_type: str, streams: List[str]) -> str:
    market_type = (market_type or 'spot').lower()
    if market_type in ('usdt_perp','coin_perp'):
        base = 'wss://fstream.binance.com/stream'
    else:
        base = 'wss://stream.binance.com:9443/stream'
    return f"{base}?streams={'/'.join(streams)}"

def _kline_streams(symbols: List[str], interval='1m') -> List[str]:
    return [f"{s.lower()}@kline_{interval}" for s in symbols]

async def kline_1m_events(symbols: List[str], market_type: str) -> AsyncIterator[dict]:
    url = _stream_url(market_type, _kline_streams(symbols, '1m'))
    backoff = 1
    while True:
        try:
            async with websockets.connect(url, ping_interval=15, ping_timeout=20) as ws:
                backoff = 1
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    payload = data.get('data') or data
                    if payload.get('e') == 'kline':
                        yield payload
        except Exception as e:
            print("WS reconnect:", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff*2, 30)
