import httpx, asyncio, os
from typing import Optional

class Notifier:
    def __init__(self, telegram_token: Optional[str], telegram_chat_id: Optional[str], webhook_url: Optional[str]):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.webhook_url = webhook_url

    async def send_json(self, payload: dict):
        if not self.webhook_url:
            return
        async with httpx.AsyncClient(timeout=10) as cli:
            try:
                await cli.post(self.webhook_url, json=payload)
            except Exception as e:
                print("Webhook error:", e)

    async def send_telegram(self, text: str):
        if not (self.telegram_token and self.telegram_chat_id):
            return
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as cli:
            try:
                await cli.post(url, data={"chat_id": self.telegram_chat_id, "text": text})
            except Exception as e:
                print("Telegram error:", e)

def fmt_signal_msg(s):
    sr_s = s["sr"]
    s_sup = sr_s.get("nearest_support")
    s_res = sr_s.get("nearest_resistance")
    sup = f"{s_sup[0]:.2f}-{s_sup[1]:.2f}" if s_sup else "None"
    res = f"{s_res[0]:.2f}-{s_res[1]:.2f}" if s_res else "None"
    ind = s["indicators"]
    return (
        f"[{s['symbol']}] {s['timeframe']} • {s['signal']} • Score {s['score']}\n"
        f"Regime: {s['regime']} | Close: {s['price']:.2f}\n"
        f"S/R: S {sup} | R {res}\n"
        f"RSI {ind.get('rsi',0):.1f} • ADX {ind.get('adx',0):.1f} • ATR {ind.get('atr',0):.1f}\n"
        f"Gợi ý: Entry {s['entry_hint']:.2f} | SL {s['sl_hint']:.2f} | TP {s['tp_hint']:.2f}\n"
        f"Lý do: {', '.join(s['rationale'][:4])}"
    )
