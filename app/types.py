from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

TF = Literal["M15","H1","H4","D1","W1"]
Direction = Literal["LONG","SHORT","NEUTRAL"]
Regime = Literal["trend_bull","trend_bear","range"]

@dataclass
class TfSignal:
    symbol: str
    timeframe: TF
    closed_at: int
    regime: Regime
    signal: Direction
    score: int
    price: float
    indicators: Dict[str, float]
    sr: Dict[str, Optional[Tuple[float,float]]]
    entry_hint: float
    sl_hint: float
    tp_hint: float
    rationale: List[str]
