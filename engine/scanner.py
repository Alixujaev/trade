from __future__ import annotations

import csv
import datetime
import json
import logging
import os

from alerts.base import AlertSink
from core.config import AppConfig
from core.models import Action, Signal
from data.base import DataSource
from signals.detectors import Setup, scan_symbol

logger = logging.getLogger(__name__)

_JOURNAL_HEADER = [
    "scanned_at",
    "bar_date",
    "symbol",
    "price",
    "triggers",
    "context",
    "confluence",
    "decision",
    "outcome",
    "notes",
]


class Scanner:
    def __init__(
        self,
        data: DataSource,
        alert: AlertSink,
        cfg: AppConfig,
        require_uptrend: bool = True,
        journal_path: str = "journal.csv",
        state_path: str = "scanner_state.json",
        drop_forming_bar: bool = True,
    ) -> None:
        self.data = data
        self.alert = alert
        self.cfg = cfg
        self.require_uptrend = require_uptrend
        self.journal_path = journal_path
        self.state_path = state_path
        self.drop_forming_bar = drop_forming_bar
        self.state: dict = self._load_state()

    def _load_state(self) -> dict:
        if not os.path.isfile(self.state_path):
            logger.warning("scanner state file %s not found; starting fresh", self.state_path)
            return {}
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "scanner state file %s is corrupt or unreadable; starting fresh",
                self.state_path,
            )
            return {}

    def _save_state(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f)

    def _append_journal(self, setup: Setup, bar_date: str, scanned_at: str) -> None:
        is_new = not os.path.isfile(self.journal_path)
        with open(self.journal_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(_JOURNAL_HEADER)
            writer.writerow(
                [
                    scanned_at,
                    bar_date,
                    setup.symbol,
                    setup.price,
                    "|".join(setup.triggers),
                    "|".join(setup.context),
                    setup.confluence,
                    "",
                    "",
                    "",
                ]
            )

    def _to_signal(self, setup: Setup, timestamp) -> Signal:
        reason = (
            "SCANNER: setup formed, go look — not a trade signal. "
            f"triggers={','.join(setup.triggers)} "
            f"context={','.join(setup.context)} "
            f"confluence={setup.confluence}"
        )
        return Signal(
            symbol=setup.symbol,
            timestamp=timestamp,
            target_position=1,
            action=Action.BUY,
            reason=reason,
            price=setup.price,
        )

    def process_symbol(self, symbol: str) -> Setup | None:
        df = self.data.get_history(symbol, self.cfg.lookback_days, self.cfg.interval)
        if self.drop_forming_bar:
            df = df.iloc[:-1]

        setup = scan_symbol(df, symbol, self.cfg, require_uptrend=self.require_uptrend)
        if setup is None:
            return None

        latest_ts = df.index[-1]
        ts_key = str(latest_ts)

        if self.state.get(symbol) == ts_key:
            return None  # already alerted this bar

        scanned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._append_journal(setup, ts_key, scanned_at)

        self.alert.send(self._to_signal(setup, latest_ts))

        # Only mark this bar "alerted" once the journal write and alert both
        # succeeded — otherwise a transient failure (e.g. disk full) would
        # permanently drop the setup, since run_once still saves state for
        # every symbol it processed, even ones whose per-symbol exception it
        # caught and logged.
        self.state[symbol] = ts_key
        return setup

    def run_once(self, symbols: list[str]) -> list[Setup]:
        setups: list[Setup] = []
        for symbol in symbols:
            try:
                setup = self.process_symbol(symbol)
                if setup is not None:
                    setups.append(setup)
            except Exception:
                logger.exception("scanner failed processing symbol %s", symbol)
        self._save_state()
        return setups
