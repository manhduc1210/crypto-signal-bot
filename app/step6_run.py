import asyncio, os
from typing import List, Dict
from .settings import Settings
from .ws_binance import kline_1m_events
from .candles import Candle, CandleAggregator
from .sr import SRDetector
from .indicators import SeriesBuffer, IndicatorParams, compute_features
from .signal_engine import decide_signal
from .alerts import Notifier, fmt_signal_msg

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
    tfs: List[str] = [x.get('tf') for x in s.raw.get('timeframes', [])]
    tf_cfg = {x.get('tf'): x for x in s.raw.get('timeframes', [])}

    ind_params = IndicatorParams(s.raw.get('indicators', {}))

    sr_cfg = s.raw.get('sr', {})
    det = SRDetector(
        pivot_window = sr_cfg.get('pivot_window', 5),
        merge_tolerance_pct = sr_cfg.get('merge_tolerance_pct', 0.1),
        merge_tolerance_atr_mult = sr_cfg.get('merge_tolerance_atr_mult', 0.5),
        max_age_bars = sr_cfg.get('max_age_bars', 300),
        decay_per_bar = sr_cfg.get('decay_per_bar', 0.01),
    )

    alerts = s.raw.get('alerts', {})
    notifier = Notifier(
        telegram_token = alerts.get('telegram_token'),
        telegram_chat_id = alerts.get('telegram_chat_id'),
        webhook_url = alerts.get('webhook_url')
    )
    enable_telegram = alerts.get('enable_telegram', True)
    enable_webhook = alerts.get('enable_webhook', False)

    buf = SeriesBuffer()
    agg = CandleAggregator(symbols, tfs)

    # snapshot cache: symbol -> tf -> last TfSignal-like dict
    last_tf_signal: Dict[str, Dict[str, dict]] = {sym: {} for sym in symbols}

    def on_close(c: Candle):
        # 1) buffer this TF candle
        buf.append(c.symbol, c.tf, c.t_close, c.o, c.h, c.l, c.c, c.v)
        # 2) compute indicators
        df = buf.df(c.symbol, c.tf)
        if len(df) < 250:  # warmup safeguard
            print(f"WARMUP {c.symbol} {c.tf} size={len(df)}")
            return
        feats = compute_features(df, ind_params)
        row = feats.iloc[-1].to_dict()
        # 3) update SR with this candle; find nearest
        det.update(c.symbol, c.tf, c.o, c.h, c.l, c.c)
        near = det.nearest(c.symbol, c.tf, c.c)
        sr_pack = {
            "nearest_support": (near["support"][0], near["support"][1]) if near.get("support") else None,
            "nearest_resistance": (near["resistance"][0], near["resistance"][1]) if near.get("resistance") else None,
        }
        # 4) decide signal
        cfg = tf_cfg.get(c.tf, {})
        adx_thr = cfg.get("adx_trend_threshold", 20)
        score_thr = cfg.get("score_threshold", 72)
        sr_near_simple = {
            "support": sr_pack["nearest_support"],
            "resistance": sr_pack["nearest_resistance"],
        }
        direction, score, regime, entry, sl, tp, reasons = decide_signal(row, adx_thr, score_thr, sr_near_simple)
        payload = {
            "symbol": c.symbol,
            "timeframe": c.tf,
            "closed_at": c.t_close,
            "regime": regime,
            "signal": direction,
            "score": score,
            "price": float(row["close"]),
            "indicators": {
                "ema_fast": float(row.get("ema_fast", 0)),
                "ema_slow": float(row.get("ema_slow", 0)),
                "rsi": float(row.get("rsi", 0)),
                "adx": float(row.get("adx", 0)),
                "atr": float(row.get("atr", 0)),
                "bb_width": float(row.get("bb_width", 0))
            },
            "sr": sr_pack,
            "entry_hint": float(entry),
            "sl_hint": float(sl),
            "tp_hint": float(tp),
            "rationale": reasons[:6],
        }

        # cache for snapshot
        last_tf_signal[c.symbol][c.tf] = payload

        # 5) publish this TF
        print(f"SIGNAL {c.symbol} {c.tf} | {direction} ({score}) | {regime} | close {payload['price']:.2f}")
        if enable_webhook:
            asyncio.create_task(notifier.send_json(payload))
        if enable_telegram:
            asyncio.create_task(notifier.send_telegram(fmt_signal_msg(payload)))

        # 6) snapshot all TFs for this symbol when we have all
        sym_cache = last_tf_signal[c.symbol]
        if all(tf in sym_cache for tf in tfs):
            # basic consensus: count non-NEUTRAL in same side for adjacent TFs
            longs = sum(1 for tf in tfs if sym_cache[tf]["signal"] == "LONG")
            shorts = sum(1 for tf in tfs if sym_cache[tf]["signal"] == "SHORT")
            if longs >= 2: consensus = "STRONG_LONG"
            elif shorts >= 2: consensus = "STRONG_SHORT"
            else: consensus = "MIXED"
            snap = {
                "symbol": c.symbol,
                "closed_at": c.t_close,
                "consensus": consensus,
                "per_tf": {tf: sym_cache[tf] for tf in tfs}
            }
            # console summary
            row_lines = [f"{tf}:{sym_cache[tf]['signal']}({sym_cache[tf]['score']}) {sym_cache[tf]['regime']}" for tf in tfs]
            print(f"[{c.symbol}] Snapshot | " + " | ".join(row_lines) + f" | Consensus: {consensus}")
            if enable_webhook:
                asyncio.create_task(notifier.send_json({"type": "snapshot", **snap}))

    agg.on_close = on_close

    print("[Step 6] Full pipeline: WS -> Roll-up -> Indicators -> SR -> Signals -> Publish")
    print("Symbols:", symbols, "Market:", market, "TFs:", tfs)
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
