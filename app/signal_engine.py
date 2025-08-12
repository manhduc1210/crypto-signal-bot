from typing import Dict, Tuple, List
import math

def _score_trend_long(row, adx_thr: float, sr: Dict):
    score = 0; reasons = []
    if row["ema_fast"] > row["ema_slow"] and row.get("adx", 0) >= adx_thr:
        score += 25; reasons.append("EMAfast>EMAslow & ADX>=thr")
    if row.get("rsi", 0) > 50:
        score += 20; reasons.append("RSI>50")
    macdh = row.get("MACDh_"+str(12)+"_"+str(26)+"_"+str(9))
    if macdh is None: macdh = row.get("MACDh_12_26_9")
    if macdh is not None and macdh > 0:
        score += 15; reasons.append("MACD_hist>0")
    # breakout over resistance with buffer 0.1*ATR
    r = sr.get("resistance")
    if r:
        r_low, r_high = r
        if row["close"] > (r_high + 0.1*row.get("atr", 0)):
            score += 30; reasons.append("Break>R+buffer")
    else:
        score += 10; reasons.append("NoR")
    # bb expansion hint
    if row.get("bb_width", 0) > 0:
        score += 0  # optional
    # entry/sl/tp
    entry = row["close"]
    # SL at nearest support or 1.5*ATR
    s = sr.get("support")
    atr = row.get("atr", 0)
    sl = entry - 1.5*atr
    if s:
        s_low, s_high = s
        sl = min(sl, s_high - 0.1*atr)
    tp = entry + 2*(entry - sl)
    return score, reasons, entry, sl, tp

def _score_trend_short(row, adx_thr: float, sr: Dict):
    score = 0; reasons = []
    if row["ema_fast"] < row["ema_slow"] and row.get("adx", 0) >= adx_thr:
        score += 25; reasons.append("EMAfast<EMAslow & ADX>=thr")
    if row.get("rsi", 100) < 50:
        score += 20; reasons.append("RSI<50")
    macdh = row.get("MACDh_12_26_9")
    if macdh is not None and macdh < 0:
        score += 15; reasons.append("MACD_hist<0")
    s = sr.get("support")
    if s:
        s_low, s_high = s
        if row["close"] < (s_low - 0.1*row.get("atr", 0)):
            score += 30; reasons.append("Break<S-buffer")
    else:
        score += 10; reasons.append("NoS")
    entry = row["close"]
    atr = row.get("atr", 0)
    r = sr.get("resistance")
    sl = entry + 1.5*atr
    if r:
        r_low, r_high = r
        sl = max(sl, r_low + 0.1*atr)
    tp = entry - 2*(sl - entry)
    return score, reasons, entry, sl, tp

def decide_signal(row, adx_thr: float, score_thr: int, sr_near: Dict):
    # sr_near expects {"support": (low,high) or None, "resistance": (low,high) or None}
    # regime
    if row["ema_fast"] > row["ema_slow"] and row.get("adx", 0) >= adx_thr:
        regime = "trend_bull"
        score, reasons, entry, sl, tp = _score_trend_long(row, adx_thr, sr_near)
        direction = "LONG" if score >= score_thr else "NEUTRAL"
    elif row["ema_fast"] < row["ema_slow"] and row.get("adx", 0) >= adx_thr:
        regime = "trend_bear"
        score, reasons, entry, sl, tp = _score_trend_short(row, adx_thr, sr_near)
        direction = "SHORT" if score >= score_thr else "NEUTRAL"
    else:
        # range: inside zone → neutral; at extremes with mild contra signals could be considered, but keep simple
        regime = "range"
        score = 50
        reasons = ["Range"]
        entry = row["close"]; sl = row["close"]; tp = row["close"]
        direction = "NEUTRAL"
    return direction, int(score), regime, entry, sl, tp, reasons
