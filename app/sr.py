from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from collections import deque
import math

@dataclass
class Zone:
    tf: str
    price_low: float
    price_high: float
    score: float
    touches: int
    last_touch_idx: int  # bar index in our local series
    created_idx: int

class SRDetector:
    """Support/Resistance zone detector using pivot-based levels merged into zones.
    - Maintain a rolling OHLC list per (symbol, tf)
    - On each new closed candle, check for pivots (high/low) at center = idx - w
    - Merge levels into zones with tolerance = max(pct * price, atr_mult * atr)
    - Update touches and score with simple decay
    """
    def __init__(self, pivot_window:int=5, merge_tolerance_pct:float=0.1, merge_tolerance_atr_mult:float=0.5,
                 max_age_bars:int=300, decay_per_bar:float=0.01):
        self.pivot_window = pivot_window
        self.merge_tol_pct = merge_tolerance_pct / 100.0  # convert percent to fraction
        self.merge_tol_atr_mult = merge_tolerance_atr_mult
        self.max_age_bars = max_age_bars
        self.decay_per_bar = decay_per_bar

        # series store: (symbol, tf) -> dict with 'o','h','l','c','atr' lists and 'zones' list
        self.store: Dict[Tuple[str,str], Dict[str, List[float] or List[Zone]]] = {}

    def _get_pair(self, symbol:str, tf:str):
        key = (symbol.upper(), tf.upper())
        if key not in self.store:
            self.store[key] = {
                "o": [], "h": [], "l": [], "c": [], "atr": [], "zones": []
            }
        return key, self.store[key]

    def _compute_atr(self, H:List[float], L:List[float], C:List[float], length:int=14) -> float:
        n = len(C)
        if n < 2:
            return 0.0
        tr = 0.0
        count = 0
        start = max(1, n - length)
        for i in range(start, n):
            high = H[i]
            low = L[i]
            prev_close = C[i-1]
            cur_tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr += cur_tr
            count += 1
        return (tr / count) if count else 0.0

    def _is_pivot_high(self, H:List[float], center:int, w:int) -> bool:
        if center - w < 0 or center + w >= len(H):
            return False
        c = H[center]
        for i in range(center - w, center + w + 1):
            if i == center: 
                continue
            if H[i] >= c: 
                return False
        return True

    def _is_pivot_low(self, L:List[float], center:int, w:int) -> bool:
        if center - w < 0 or center + w >= len(L):
            return False
        c = L[center]
        for i in range(center - w, center + w + 1):
            if i == center: 
                continue
            if L[i] <= c: 
                return False
        return True

    def _merge_or_create_zone(self, zones:List[Zone], tf:str, level:float, atr:float, cur_idx:int):
        # tolerance width around a level
        tol = max(level * self.merge_tol_pct, self.merge_tol_atr_mult * atr)
        z_low = level - tol
        z_high = level + tol

        # try to merge with overlapping zone
        merged = False
        for z in zones:
            if not (z_high < z.price_low or z_low > z.price_high):
                # overlap -> expand bounds
                z.price_low = min(z.price_low, z_low)
                z.price_high = max(z.price_high, z_high)
                z.touches += 1
                z.score += 1.0  # basic increment, will be decayed later
                z.last_touch_idx = cur_idx
                merged = True
                break

        if not merged:
            zones.append(Zone(tf=tf, price_low=z_low, price_high=z_high, score=1.0, touches=1,
                              last_touch_idx=cur_idx, created_idx=cur_idx))

    def update(self, symbol:str, tf:str, o:float, h:float, l:float, c:float):
        key, slot = self._get_pair(symbol, tf)
        O,H,L,C = slot["o"], slot["h"], slot["l"], slot["c"]
        O.append(o); H.append(h); L.append(l); C.append(c)

        # ATR (simple rolling) for tolerance
        atr = self._compute_atr(H, L, C, length=14)
        slot["atr"].append(atr)
        zones = slot["zones"]
        idx = len(C) - 1

        # Decay & prune zones
        for z in zones:
            z.score = max(0.0, z.score * (1.0 - self.decay_per_bar))
        # Drop very old zones (based on created age)
        slot["zones"] = [z for z in zones if (idx - z.created_idx) <= self.max_age_bars]
        zones = slot["zones"]

        w = self.pivot_window
        center = idx - w  # we can confirm a pivot w bars ago
        if center >= 0:
            if self._is_pivot_high(H, center, w):
                level = H[center]
                self._merge_or_create_zone(zones, tf, level, atr, center)
            if self._is_pivot_low(L, center, w):
                level = L[center]
                self._merge_or_create_zone(zones, tf, level, atr, center)

        # Touch update: if close is inside a zone, count a touch and bump score
        for z in zones:
            if z.price_low <= c <= z.price_high:
                z.touches += 1
                z.score += 0.5
                z.last_touch_idx = idx

    def nearest(self, symbol:str, tf:str, price:float) -> Dict[str, Optional[Tuple[float,float,Zone]]]:
        key, slot = self._get_pair(symbol, tf)
        zones: List[Zone] = slot["zones"]
        if not zones:
            return {"support": None, "resistance": None}

        below = [z for z in zones if z.price_high <= price]
        above = [z for z in zones if z.price_low >= price]

        def dist_to_zone(p, z:Zone):
            if p < z.price_low:
                return z.price_low - p
            if p > z.price_high:
                return p - z.price_high
            return 0.0

        support = None
        if below:
            support = min(below, key=lambda z: dist_to_zone(price, z))
        resistance = None
        if above:
            resistance = min(above, key=lambda z: dist_to_zone(price, z))

        s_tuple = (support.price_low, support.price_high, support) if support else None
        r_tuple = (resistance.price_low, resistance.price_high, resistance) if resistance else None
        return {"support": s_tuple, "resistance": r_tuple}
