from dataclasses import dataclass, field
from typing import Dict, Tuple, List
from collections import deque
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

def compute_features(df: pd.DataFrame, p: IndicatorParams) -> pd.DataFrame:
    out = df.copy()
    out['ema_fast'] = ta.ema(out['close'], length=p.ema_fast)
    out['ema_slow'] = ta.ema(out['close'], length=p.ema_slow)
    out['rsi'] = ta.rsi(out['close'], length=p.rsi_length)
    macd = ta.macd(out['close'], fast=p.macd_fast, slow=p.macd_slow, signal=p.macd_signal)
    if macd is not None and not macd.empty:
        out = out.join(macd)
    bb = ta.bbands(out['close'], length=p.bb_length, std=p.bb_std)
    if bb is not None and not bb.empty:
        out = out.join(bb)
    out['atr'] = ta.atr(out['high'], out['low'], out['close'], length=p.atr_length)
    adx = ta.adx(out['high'], out['low'], out['close'], length=p.adx_length)
    if adx is not None and not adx.empty:
        out = out.join(adx['ADX_'+str(p.adx_length)].rename('adx'))
    out['trend_bull'] = (out['ema_fast'] > out['ema_slow']) & (out['adx'] > 20)
    out['trend_bear'] = (out['ema_fast'] < out['ema_slow']) & (out['adx'] > 20)
    return out

@dataclass
class SeriesBuffer:
    limit: int = 2000
    store: Dict[Tuple[str,str], deque] = field(default_factory=dict)

    def append(self, symbol: str, tf: str, candle_dict: Dict):
        key = (symbol.upper(), tf.upper())
        if key not in self.store:
            self.store[key] = deque(maxlen=self.limit)
        self.store[key].append(candle_dict)

    def to_df(self, symbol: str, tf: str) -> pd.DataFrame:
        key = (symbol.upper(), tf.upper())
        arr = list(self.store.get(key, []))
        if not arr:
            return pd.DataFrame(columns=['ts','open','high','low','close','volume'])
        df = pd.DataFrame(arr)
        df = df.sort_values('t_close')
        df = df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume','t_close':'ts'})
        return df
