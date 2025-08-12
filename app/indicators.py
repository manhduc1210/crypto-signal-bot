import pandas as pd
import pandas_ta as ta

class IndicatorParams:
    def __init__(self, cfg: dict):
        self.ema_fast = cfg.get("ema_fast", 50)
        self.ema_slow = cfg.get("ema_slow", 200)
        self.rsi_len = cfg.get("rsi_length", 14)
        self.macd_fast = cfg.get("macd_fast", 12)
        self.macd_slow = cfg.get("macd_slow", 26)
        self.macd_signal = cfg.get("macd_signal", 9)
        self.bb_len = cfg.get("bb_length", 20)
        self.bb_std = cfg.get("bb_std", 2)
        self.atr_len = cfg.get("atr_length", 14)
        self.adx_len = cfg.get("adx_length", 14)

def compute_features(df: pd.DataFrame, p: IndicatorParams) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ta.ema(out["close"], length=p.ema_fast)
    out["ema_slow"] = ta.ema(out["close"], length=p.ema_slow)
    out["rsi"] = ta.rsi(out["close"], length=p.rsi_len)
    macd = ta.macd(out["close"], fast=p.macd_fast, slow=p.macd_slow, signal=p.macd_signal)
    if macd is not None:
        out = out.join(macd)
    bb = ta.bbands(out["close"], length=p.bb_len, std=p.bb_std)
    if bb is not None:
        out = out.join(bb)
        out["bb_width"] = (out["BBU_"+str(p.bb_len)+"_"+str(p.bb_std)] - out["BBL_"+str(p.bb_len)+"_"+str(p.bb_std)]) / out["close"]
    out["atr"] = ta.atr(out["high"], out["low"], out["close"], length=p.atr_len)
    adx = ta.adx(out["high"], out["low"], out["close"], length=p.adx_len)
    if adx is not None:
        out["adx"] = adx["ADX_"+str(p.adx_len)]
    # regime flags
    out["trend_bull"] = (out["ema_fast"] > out["ema_slow"]) & (out["adx"] > 0)
    out["trend_bear"] = (out["ema_fast"] < out["ema_slow"]) & (out["adx"] > 0)
    return out

class SeriesBuffer:
    def __init__(self):
        self.store = {}  # (symbol, tf) -> list[dict]
    def append(self, symbol: str, tf: str, t_close: int, o: float, h: float, l: float, c: float, v: float):
        key = (symbol.upper(), tf.upper())
        self.store.setdefault(key, []).append({"t": t_close, "open": o, "high": h, "low": l, "close": c, "volume": v})
        # limit size
        if len(self.store[key]) > 5000:
            self.store[key] = self.store[key][-4000:]
    def df(self, symbol: str, tf: str) -> pd.DataFrame:
        key = (symbol.upper(), tf.upper())
        arr = self.store.get(key, [])
        if not arr:
            return pd.DataFrame(columns=["t","open","high","low","close","volume"]).set_index("t")
        df = pd.DataFrame(arr)
        df = df.set_index("t")
        return df
