import asyncio
from typing import List, Dict
from .settings import Settings
from .ws_binance import kline_1m_events
from .candles import Candle, CandleAggregator
from .sr import SRDetector

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

    sr_cfg = s.raw.get('sr', {})
    det = SRDetector(
        pivot_window = sr_cfg.get('pivot_window', 5),
        merge_tolerance_pct = sr_cfg.get('merge_tolerance_pct', 0.1),
        merge_tolerance_atr_mult = sr_cfg.get('merge_tolerance_atr_mult', 0.5),
        max_age_bars = sr_cfg.get('max_age_bars', 300),
        decay_per_bar = sr_cfg.get('decay_per_bar', 0.01),
    )

    print("[Step 4] WS + Roll-up + SR zones (nearest S/R on TF close)")
    print("Symbols:", symbols, " Market:", market, " TFs:", tfs)

    agg = CandleAggregator(symbols, tfs)

    def on_close(c: Candle):
        # Update detector with closed TF candle
        det.update(c.symbol, c.tf, c.o, c.h, c.l, c.c)
        nr = det.nearest(c.symbol, c.tf, c.c)
        s = nr.get("support")
        r = nr.get("resistance")
        s_str = f"{s[0]:.2f}-{s[1]:.2f} (score {s[2].score:.1f}, touches {s[2].touches})" if s else "None"
        r_str = f"{r[0]:.2f}-{r[1]:.2f} (score {r[2].score:.1f}, touches {r[2].touches})" if r else "None"
        print(f"S/R {c.symbol} {c.tf} close={c.c:.2f} | S={s_str} | R={r_str}")

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
