from dataclasses import dataclass
from typing import Dict, List, Literal

TFDirection = Literal["LONG","SHORT","NEUTRAL"]
Regime = Literal["trend_bull","trend_bear","range"]

@dataclass
class TfSignal:
    symbol: str
    timeframe: str
    closed_at: int  # ms epoch (TF t_close)
    trend_regime: Regime
    signal: TFDirection
    score: int
    price: float
    indicators: Dict[str, float]
    sr: Dict
    entry_hint: float
    sl_hint: float
    tp_hint: float
    rationale: List[str]
