from __future__ import annotations

import logging

import requests

from alerts.base import AlertSink
from core.models import Action, Signal

logger = logging.getLogger(__name__)

_ACTION_EMOJI = {
    Action.BUY: "\U0001f7e2",  # green circle
    Action.SELL: "\U0001f534",  # red circle
    Action.HOLD: "⚪",  # white circle
}


class TelegramAlertSink(AlertSink):
    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    def send(self, signal: Signal) -> None:
        if signal.formatted_text is not None:
            # Pre-built by the caller (e.g. the scanner) -- send verbatim
            # rather than wrapping it in the generic strategy-alert template.
            text = signal.formatted_text
        else:
            emoji = _ACTION_EMOJI.get(signal.action, "")
            text = (
                f"{emoji} <b>{signal.action.value}</b> {signal.symbol}\n"
                f"Price: {signal.price}\n"
                f"Date: {signal.timestamp}\n"
                f"Reason: {signal.reason}\n\n"
                f"<i>Signal only — no order placed.</i>"
            )
        url = self.API_URL.format(token=self.token)
        try:
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            logger.exception("failed to send telegram alert for %s", signal.symbol)
