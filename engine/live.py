from __future__ import annotations

import json
import logging
import os

from alerts.base import AlertSink
from core.config import AppConfig
from core.models import Action, Signal
from data.base import DataSource
from signals.base import Strategy

logger = logging.getLogger(__name__)


class LiveEngine:
    def __init__(
        self,
        data: DataSource,
        strategy: Strategy,
        alert: AlertSink,
        cfg: AppConfig,
        drop_forming_bar: bool = True,
    ) -> None:
        self.data = data
        self.strategy = strategy
        self.alert = alert
        self.cfg = cfg
        self.drop_forming_bar = drop_forming_bar
        self.state: dict = self._load_state()

    def _load_state(self) -> dict:
        path = self.cfg.state_file
        if not os.path.isfile(path):
            logger.warning("state file %s not found; starting fresh", path)
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("state file %s is corrupt or unreadable; starting fresh", path)
            return {}

    def _save_state(self) -> None:
        with open(self.cfg.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f)

    def process_symbol(self, symbol: str) -> Signal | None:
        df = self.data.get_history(symbol, self.cfg.lookback_days, self.cfg.interval)
        if self.drop_forming_bar:
            df = df.iloc[:-1]

        target = self.strategy.target_position(df)
        latest_target = int(target.iloc[-1])
        latest_ts = df.index[-1]
        latest_price = float(df["close"].iloc[-1])

        prev_position = int(self.state.get(symbol, 0))
        self.state[symbol] = latest_target

        if latest_target == prev_position:
            return None

        action = Action.BUY if latest_target > prev_position else Action.SELL
        signal = Signal(
            symbol=symbol,
            timestamp=latest_ts,
            target_position=latest_target,
            action=action,
            reason=(
                f"{self.strategy.name} target position changed "
                f"{prev_position} -> {latest_target}"
            ),
            price=latest_price,
        )
        self.alert.send(signal)
        return signal

    def run_once(self, symbols: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol in symbols:
            try:
                signal = self.process_symbol(symbol)
                if signal is not None:
                    signals.append(signal)
            except Exception:
                logger.exception("failed processing symbol %s", symbol)
        self._save_state()
        return signals
