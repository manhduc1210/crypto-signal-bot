from dataclasses import dataclass
from typing import Dict, List, Tuple
import pandas as pd
import pandas_ta as ta

@dataclass
class IndicatorParams:
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_length: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_length: int = 20
    bb_std: float = 2.0
    atr_length: int = 14
    adx_length: int = 14

class SeriesBuffer:
    """Keep recent closed candles per (symbol, tf) and build DataFrame for indicators."""
    def __init__(self, maxlen:int=2000):
        self.maxlen = maxlen
        self.store: Dict[Tuple[str,str], Dict[str, List[float]]] = {}

    def append(self, symbol:str, tf:str, o:float, h:float, l:float, c:float, v:float):
        key = (symbol.upper(), tf.upper())
        slot = self.store.setdefault(key, {"open":[], "high":[], "low":[], "close":[], "volume":[]})
        for k,val in zip(["open","high","low","close","volume"], [o,h,l,c,v]):
            slot[k].append(val)
            if len(slot[k]) > self.maxlen:
                slot[k].pop(0)

    def get_df(self, symbol:str, tf:str) -> pd.DataFrame:
        key = (symbol.upper(), tf.upper())
        slot = self.store.get(key, None)
        if not slot or len(slot.get("close",[])) < 5:
            return pd.DataFrame(columns=["open","high","low","close","volume"])
        df = pd.DataFrame(slot)
        return df

def compute_features(df: pd.DataFrame, p: IndicatorParams) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["ema_fast"] = ta.ema(out["close"], length=p.ema_fast)
    out["ema_slow"] = ta.ema(out["close"], length=p.ema_slow)
    out["rsi"] = ta.rsi(out["close"], length=p.rsi_length)
    macd = ta.macd(out["close"], fast=p.macd_fast, slow=p.macd_slow, signal=p.macd_signal)
    out = out.join(macd)
    bb = ta.bbands(out["close"], length=p.bb_length, std=p.bb_std)
    out = out.join(bb)
    out["atr"] = ta.atr(out["high"], out["low"], out["close"], length=p.atr_length)
    adx = ta.adx(out["high"], out["low"], out["close"], length=p.adx_length)
    out["adx"] = adx[f"ADX_{p.adx_length}"]
    # bb width
    if all(col in out for col in ["BBU_20_2.0","BBL_20_2.0"]):
        out["bb_width"] = (out["BBU_20_2.0"] - out["BBL_20_2.0"]) / out["close"]
    else:
        out["bb_width"] = None
    # regime flags will be decided in signal engine using thresholds from config
    return out
