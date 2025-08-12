import asyncio, time
from typing import List, Dict, Tuple
import pandas as pd
from .settings import Settings
from .ws_binance import kline_1m_events
from .candles import Candle, CandleAggregator
from .sr import SRDetector
from .indicators import SeriesBuffer, IndicatorParams, compute_features
from .signal_engine import decide_signal
from .types import TfSignal

def _to_f(x): return float(x) if x is not None else 0.0

def _kline_to_1m(symbol: str, k: dict) -> Candle:
    return Candle(
        symbol=symbol.upper(), tf='1m',
        t_open=int(k['t']), t_close=int(k['T']),
        o=_to_f(k['o']), h=_to_f(k['h']), l=_to_f(k['l']), c=_to_f(k['c']),
        v=_to_f(k['v']), closed=bool(k.get('x', False))
    )

def _ind_params(cfg: Dict) -> IndicatorParams:
    return IndicatorParams(
        ema_fast = cfg.get('ema_fast', 50),
        ema_slow = cfg.get('ema_slow', 200),
        rsi_length = cfg.get('rsi_length', 14),
        macd_fast = cfg.get('macd_fast', 12),
        macd_slow = cfg.get('macd_slow', 26),
        macd_signal = cfg.get('macd_signal', 9),
        bb_length = cfg.get('bb_length', 20),
        bb_std = cfg.get('bb_std', 2.0),
        atr_length = cfg.get('atr_length', 14),
        adx_length = cfg.get('adx_length', 14),
    )

async def run():
    s = Settings.load()
    ex = s.raw.get('exchange', {})
    symbols: List[str] = [x.upper() for x in ex.get('symbols', ['BTCUSDT'])]
    market = ex.get('market_type', 'spot')
    tfs_cfg = s.raw.get('timeframes', [])
    tfs = [x.get('tf') for x in tfs_cfg]
    ind_p = _ind_params(s.raw.get('indicators', {}))

    sr_cfg = s.raw.get('sr', {})
    det = SRDetector(
        pivot_window = sr_cfg.get('pivot_window', 5),
        merge_tolerance_pct = sr_cfg.get('merge_tolerance_pct', 0.1),
        merge_tolerance_atr_mult = sr_cfg.get('merge_tolerance_atr_mult', 0.5),
        max_age_bars = sr_cfg.get('max_age_bars', 300),
        decay_per_bar = sr_cfg.get('decay_per_bar', 0.01),
    )

    buf = SeriesBuffer(maxlen=3000)
    last_signals: Dict[Tuple[str,str], TfSignal] = {}

    print("[Step 5] WS + Roll-up + Indicators + S/R + Signal Engine")
    print("Symbols:", symbols, " Market:", market, " TFs:", tfs)

    agg = CandleAggregator(symbols, tfs)

    def on_close(c: Candle):
        # 1) update buffers and SR
        buf.append(c.symbol, c.tf, c.o, c.h, c.l, c.c, c.v)
        det.update(c.symbol, c.tf, c.o, c.h, c.l, c.c)

        # 2) build df and compute features
        df = buf.get_df(c.symbol, c.tf)
        if df.empty:
            return
        feats = compute_features(df, ind_p)
        row = feats.iloc[-1].to_dict()
        row["close"] = df["close"].iloc[-1]

        # 3) nearest S/R
        sr = det.nearest(c.symbol, c.tf, row["close"])

        # 4) thresholds per TF
        tf_cfg = next((x for x in tfs_cfg if x.get("tf")==c.tf), {})
        thresholds = {
            "adx_trend_threshold": tf_cfg.get("adx_trend_threshold", 20),
            "score_threshold": tf_cfg.get("score_threshold", 70),
        }

        # 5) decide signal
        best = decide_signal(row, sr, thresholds)
        direction = best["signal"]
        score = int(best["score"])
        regime = best["regime"]
        entry, sl, tp = best["entry"], best["sl"], best["tp"]
        rationale = best["rationale"]

        # score gate
        if score < thresholds["score_threshold"]:
            direction = "NEUTRAL"

        sig = TfSignal(
            symbol=c.symbol, timeframe=c.tf, closed_at=c.t_close,
            trend_regime=regime, signal=direction, score=score,
            price=row["close"],
            indicators={
                "ema_fast": row.get("ema_fast"),
                "ema_slow": row.get("ema_slow"),
                "rsi14": row.get("rsi"),
                "adx14": row.get("adx"),
                "atr14": row.get("atr"),
                "macd_hist": row.get("MACDh_12_26_9"),
                "bb_width": row.get("bb_width"),
            },
            sr={
                "nearest_support": list(sr["support"][:2]) if sr.get("support") else None,
                "nearest_resistance": list(sr["resistance"][:2]) if sr.get("resistance") else None,
            },
            entry_hint=entry, sl_hint=sl, tp_hint=tp, rationale=rationale[:6]
        )
        last_signals[(c.symbol, c.tf)] = sig

        # 6) print per-TF signal
        sup = sig.sr.get("nearest_support")
        res = sig.sr.get("nearest_resistance")
        sup_str = f"{sup[0]:.2f}-{sup[1]:.2f}" if sup else "None"
        res_str = f"{res[0]:.2f}-{res[1]:.2f}" if res else "None"
        print(f"SIGNAL {sig.symbol} {sig.timeframe} | {sig.signal} (score {sig.score}) "
              f"| regime {sig.trend_regime} | close {sig.price:.2f} | S {sup_str} | R {res_str} "
              f"| reasons: {', '.join(sig.rationale)}")

        # 7) snapshot (optional minimal)
        # collect all TFs for this symbol
        per_tf = [last_signals.get((c.symbol, tf)) for tf in tfs]
        if all(per_tf):
            # simple consensus: if >=2 adjacent TFs align with LONG/SHORT at/above threshold
            sides = [s.signal for s in per_tf]
            strong = "MIXED"
            if sides.count("LONG") >= 2:
                strong = "STRONG_LONG"
            elif sides.count("SHORT") >= 2:
                strong = "STRONG_SHORT"
            line = [f"[{c.symbol}] Snapshot"]
            for s in per_tf:
                line.append(f"{s.timeframe}:{s.signal}({s.score}) {s.trend_regime}")
            line.append(f"Consensus: {strong}")
            print(" | ".join(line))

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
