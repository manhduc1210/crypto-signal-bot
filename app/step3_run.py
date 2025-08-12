import asyncio
from .settings import Settings
from .ws_binance import kline_1m_events
from .candles import Candle, CandleAggregator
from .indicators import IndicatorParams, SeriesBuffer, compute_features

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
    symbols = [x.upper() for x in ex.get('symbols', ['BTCUSDT'])]
    market = ex.get('market_type', 'spot')
    tfs = [x.get('tf') for x in s.raw.get('timeframes', [])]
    ip = s.raw.get('indicators', {})
    params = IndicatorParams(
        ema_fast=ip.get('ema_fast',50), ema_slow=ip.get('ema_slow',200),
        rsi_length=ip.get('rsi_length',14), macd_fast=ip.get('macd_fast',12),
        macd_slow=ip.get('macd_slow',26), macd_signal=ip.get('macd_signal',9),
        bb_length=ip.get('bb_length',20), bb_std=ip.get('bb_std',2.0),
        atr_length=ip.get('atr_length',14), adx_length=ip.get('adx_length',14)
    )

    print('[Step 3] Ingestion + Indicators on TF close:', symbols, tfs)
    agg = CandleAggregator(symbols, tfs)
    buf = SeriesBuffer(limit=3000)

    def on_close(c: Candle):
        buf.append(c.symbol, c.tf, {
            't_close': c.t_close, 'o': c.o, 'h': c.h, 'l': c.l, 'c': c.c, 'v': c.v
        })
        df = buf.to_df(c.symbol, c.tf)
        if len(df) < max(params.ema_fast, params.ema_slow, params.rsi_length, params.atr_length, params.adx_length, params.bb_length, params.macd_slow):
            print(f'IND {c.symbol} {c.tf} | warmup {len(df)} bars...')
            return
        feats = compute_features(df, params)
        row = feats.iloc[-1]
        regime = 'range'
        if bool(row.get('trend_bull')): regime = 'trend_bull'
        elif bool(row.get('trend_bear')): regime = 'trend_bear'
        macd_hist = None
        for col in feats.columns[::-1]:
            if 'MACDh' in col or 'MACD_Hist' in col or col.lower().startswith('macdh_'):
                macd_hist = row[col]
                break
        mh = float('nan') if macd_hist is None else macd_hist
        print(f"IND {c.symbol} {c.tf} | close={c.c:.2f} ema{int(params.ema_fast)}={row['ema_fast']:.2f} "
              f"ema{int(params.ema_slow)}={row['ema_slow']:.2f} rsi={row['rsi']:.1f} "
              f"adx={row.get('adx', float('nan')):.1f} atr={row['atr']:.2f} macd_h={mh:.2f} "
              f"regime={regime}")

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
