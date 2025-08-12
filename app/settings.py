import yaml, os, re
from dataclasses import dataclass, field
from typing import Any, Dict

ENV = re.compile(r"\$\{([A-Z0-9_]+)\}")

def _expand(x):
    if isinstance(x, str):
        m = ENV.search(x)
        if m:
            return os.environ.get(m.group(1), x)
        return x
    if isinstance(x, dict):
        return {k:_expand(v) for k,v in x.items()}
    if isinstance(x, list):
        return [_expand(v) for v in x]
    return x

@dataclass
class Settings:
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path="config/config.yaml"):
        with open(path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        return cls(raw=_expand(cfg))

    def summary(self):
        ex = self.raw.get('exchange', {})
        tfs = [x.get('tf') for x in self.raw.get('timeframes', [])]
        return f"Exchange={ex.get('name')} {ex.get('market_type')} | Symbols={ex.get('symbols')} | TFs={tfs}"
