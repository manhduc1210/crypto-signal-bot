import asyncio
from typing import List
from .settings import Settings
from .ws_binance import kline_1m_events
from .candles import Candle, CandleAggregator

def _to_f(x): return float(x) if x is not None else 0.0

def _kline_to_1m(symbol: str, k: dict) -> Candle:
    return Candle(
        symbol=symbol.upper(), tf='1m',
        t_open=int(k['t']), t_close=int(k['T']),
        o=_to_f(k['o']), h=_to_f(k['h']), l=_to_f(k['l']), c=_to_f(k['c']),
        v=_to_f(k['v']), closed=bool(k.get('x', False))
    )

async def run():
    s = Settings.load()
    ex = s.raw.get('exchange', {})
    symbols: List[str] = [x.upper() for x in ex.get('symbols', ['BTCUSDT'])]
    market = ex.get('market_type', 'spot')
    tfs = [x.get('tf') for x in s.raw.get('timeframes', [])]

    print("[Step 2] WebSocket ingestion started:", symbols, market, "TFs:", tfs)
    agg = CandleAggregator(symbols, tfs)

    def on_close(c: Candle):
        print(f"CLOSE {c.symbol} {c.tf} | o={c.o:.2f} h={c.h:.2f} l={c.l:.2f} c={c.c:.2f} v={c.v:.4f} t_close={c.t_close}")

    agg.on_close = on_close

    async for ev in kline_1m_events(symbols, market):
        k = ev.get('k', {})
        if not k.get('x', False):
            continue
        symbol = (ev.get('s') or k.get('s') or '').upper()
        if symbol not in symbols:
            continue
        c1m = _kline_to_1m(symbol, k)
        agg.ingest_1m(symbol, c1m)

if __name__ == '__main__':
    asyncio.run(run())
