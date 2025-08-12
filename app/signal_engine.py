from typing import Dict, Tuple, List
import math

def _regime(row: dict, adx_threshold: float) -> str:
    ema_fast = row.get("ema_fast")
    ema_slow = row.get("ema_slow")
    adx = row.get("adx")
    if ema_fast is None or ema_slow is None or adx is None:
        return "range"
    if ema_fast > ema_slow and adx >= adx_threshold:
        return "trend_bull"
    if ema_fast < ema_slow and adx >= adx_threshold:
        return "trend_bear"
    return "range"

def _trend_pullback_long(row, sr) -> Tuple[int, List[str], float, float, float]:
    score = 0; reasons=[]
    if row.get("ema_fast") and row.get("ema_slow") and row["ema_fast"] > row["ema_slow"]:
        score += 25; reasons.append("EMAfast>EMAslow")
    if row.get("rsi") and row["rsi"] > 50: 
        score += 25; reasons.append("RSI>50")
    macdh = row.get("MACDh_12_26_9")
    if macdh is not None and macdh > 0:
        score += 20; reasons.append("MACD_hist>0")
    # S/R context: price above nearest resistance (breakout) or safe distance
    price = row["close"]
    atr = row.get("atr") or 0.0
    res = sr.get("resistance")
    if res:
        res_low, res_high, _ = res
        if price > res_high + 0.1*atr:
            score += 30; reasons.append("Break>R+buffer")
    else:
        score += 10; reasons.append("No nearby R")
    entry = price
    # SL: below support or 1.5*ATR
    sup = sr.get("support")
    if sup:
        sup_low, sup_high, _ = sup
        sl = min(sup_high - 0.1*atr, price - 1.5*atr)
    else:
        sl = price - 1.5*atr
    tp = entry + 2*(entry - sl)
    return score, reasons, entry, sl, tp

def _trend_pullback_short(row, sr) -> Tuple[int, List[str], float, float, float]:
    score = 0; reasons=[]
    if row.get("ema_fast") and row.get("ema_slow") and row["ema_fast"] < row["ema_slow"]:
        score += 25; reasons.append("EMAfast<EMAslow")
    if row.get("rsi") and row["rsi"] < 50: 
        score += 25; reasons.append("RSI<50")
    macdh = row.get("MACDh_12_26_9")
    if macdh is not None and macdh < 0:
        score += 20; reasons.append("MACD_hist<0")
    price = row["close"]
    atr = row.get("atr") or 0.0
    sup = sr.get("support")
    if sup:
        sup_low, sup_high, _ = sup
        if price < sup_low - 0.1*atr:
            score += 30; reasons.append("Break<S-buffer")
    else:
        score += 10; reasons.append("No nearby S")
    entry = price
    res = sr.get("resistance")
    if res:
        res_low, res_high, _ = res
        sl = max(res_low + 0.1*atr, price + 1.5*atr)
    else:
        sl = price + 1.5*atr
    tp = entry - 2*(sl - entry)
    return score, reasons, entry, sl, tp

def _range_reversal(row, sr, side: str) -> Tuple[int, List[str], float, float, float]:
    # side: "LONG" if near support, "SHORT" if near resistance
    score = 0; reasons=[]
    price = row["close"]; atr = row.get("atr") or 0.0
    rsi = row.get("rsi")
    macdh = row.get("MACDh_12_26_9")
    if side == "LONG":
        sup = sr.get("support")
        if sup:
            sup_low, sup_high, _ = sup
            if sup_low - 0.1*atr <= price <= sup_high + 0.1*atr:
                score += 40; reasons.append("AtSupportZone")
        if rsi and rsi < 45: score += 15; reasons.append("RSI<45")
        if macdh is not None and macdh > -0.0: score += 10; reasons.append("MACD_hist>=0")
        entry = price
        sl = (sup_high - 0.1*atr) if sup else price - 1.2*atr
        tp = price + 2*(price - sl)
    else:  # SHORT
        res = sr.get("resistance")
        if res:
            res_low, res_high, _ = res
            if res_low - 0.1*atr <= price <= res_high + 0.1*atr:
                score += 40; reasons.append("AtResistanceZone")
        if rsi and rsi > 55: score += 15; reasons.append("RSI>55")
        if macdh is not None and macdh < 0.0: score += 10; reasons.append("MACD_hist<=0")
        entry = price
        sl = (res_low + 0.1*atr) if res else price + 1.2*atr
        tp = price - 2*(sl - price)
    return score, reasons, entry, sl, tp

def decide_signal(row: dict, sr: dict, thresholds: dict) -> Dict:
    """Return dict with keys: signal, score, regime, entry/sl/tp, rationale."""
    adx_thr = thresholds.get("adx_trend_threshold", 20)
    regime = _regime(row, adx_thr)
    price = row["close"]
    best = {"signal":"NEUTRAL", "score":0, "regime":regime,
            "entry":price, "sl":price, "tp":price, "rationale":[]}

    if regime == "trend_bull":
        s, r, e, sl, tp = _trend_pullback_long(row, sr)
        if s > best["score"]:
            best = {"signal":"LONG","score":s,"regime":regime,"entry":e,"sl":sl,"tp":tp,"rationale":r}
    elif regime == "trend_bear":
        s, r, e, sl, tp = _trend_pullback_short(row, sr)
        if s > best["score"]:
            best = {"signal":"SHORT","score":s,"regime":regime,"entry":e,"sl":sl,"tp":tp,"rationale":r}
    else:
        # range: choose side based on proximity
        sup = sr.get("support"); res = sr.get("resistance")
        # pick nearer side
        dist_s = abs(price - sup[1]) if sup else 1e9  # to upper bound of support
        dist_r = abs(res[0] - price) if res else 1e9  # to lower bound of resistance
        if dist_s < dist_r:
            s, r, e, sl, tp = _range_reversal(row, sr, "LONG")
            if s > best["score"]:
                best = {"signal":"LONG","score":s,"regime":regime,"entry":e,"sl":sl,"tp":tp,"rationale":r}
        else:
            s, r, e, sl, tp = _range_reversal(row, sr, "SHORT")
            if s > best["score"]:
                best = {"signal":"SHORT","score":s,"regime":regime,"entry":e,"sl":sl,"tp":tp,"rationale":r}
    return best
