from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class ShariaFilter:
    def __init__(self, whitelist: set[str]) -> None:
        self.whitelist = whitelist

    @classmethod
    def from_file(cls, path: str) -> ShariaFilter:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"whitelist file not found: {path}")

        symbols: set[str] = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                symbols.add(line)

        if not symbols:
            raise ValueError(f"whitelist file is empty: {path}")

        return cls(symbols)

    def is_allowed(self, symbol: str) -> bool:
        return symbol in self.whitelist

    def filter(self, symbols: list[str]) -> list[str]:
        allowed = []
        for symbol in symbols:
            if self.is_allowed(symbol):
                allowed.append(symbol)
            else:
                logger.warning("symbol %s is not on the sharia whitelist; skipping", symbol)
        return allowed
