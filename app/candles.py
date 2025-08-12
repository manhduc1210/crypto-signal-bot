from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Callable, List
from datetime import datetime, timezone, timedelta

@dataclass
class Candle:
    symbol: str
    tf: str
    t_open: int
    t_close: int
    o: float
    h: float
    l: float
    c: float
    v: float
    closed: bool = False

def _tf_minutes(tf: str) -> int:
    tf = tf.upper()
    if tf in ("1M","1MIN","1MINUTE","1"): return 1
    if tf == "M15": return 15
    if tf == "H1": return 60
    if tf == "H4": return 240
    if tf == "D1": return 1440
    if tf == "W1": return 10080
    raise ValueError(f"Unsupported TF: {tf}")

def _align_open(ts_ms: int, tf: str) -> int:
    mins = _tf_minutes(tf)
    if tf == "W1":
        dt = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
        monday = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        delta_min = int((dt - monday).total_seconds() // 60)
        aligned_min = delta_min - (delta_min % mins)
        aligned = monday + timedelta(minutes=aligned_min)
        return int(aligned.timestamp() * 1000)
    else:
        period_ms = _tf_minutes(tf) * 60_000
        return (ts_ms // period_ms) * period_ms

def _end_from_open(t_open_ms: int, tf: str) -> int:
    return t_open_ms + _tf_minutes(tf) * 60_000

class CandleAggregator:
    def __init__(self, symbols: List[str], tfs: List[str]):
        self.symbols = [s.upper() for s in symbols]
        self.tfs = [tf.upper() for tf in tfs]
        self._active: Dict[Tuple[str,str], Candle] = {}
        self._last_closed: Dict[Tuple[str,str], Candle] = {}
        self.on_close: Optional[Callable[[Candle], None]] = None

    def last_closed(self, symbol: str, tf: str) -> Optional[Candle]:
        return self._last_closed.get((symbol.upper(), tf.upper()))

    def ingest_1m(self, symbol: str, one_min: Candle):
        symbol = symbol.upper()
        if one_min.tf not in ("1m","1M","1"):
            raise ValueError("ingest_1m expects a 1m Candle")
        for tf in self.tfs:
            self._roll(symbol, tf, one_min)

    def _roll(self, symbol: str, tf: str, c1m: Candle):
        t_open_tf = _align_open(c1m.t_open, tf)
        t_close_tf = _end_from_open(t_open_tf, tf)
        key = (symbol, tf)
        cur = self._active.get(key)

        if cur is None or cur.t_open != t_open_tf:
            cur = Candle(symbol, tf, t_open_tf, t_close_tf, c1m.o, c1m.h, c1m.l, c1m.c, c1m.v, False)
            self._active[key] = cur
        else:
            cur.h = max(cur.h, c1m.h)
            cur.l = min(cur.l, c1m.l)
            cur.c = c1m.c
            cur.v += c1m.v

        if c1m.t_close >= cur.t_close:
            cur.closed = True
            self._last_closed[key] = cur
            if self.on_close:
                try:
                    self.on_close(cur)
                except Exception as e:
                    print("on_close error:", e)
            self._active[key] = None
