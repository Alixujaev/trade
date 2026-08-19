from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]+$")


def add_to_whitelist(path: str, symbol: str) -> bool:
    """Append `symbol` to the whitelist file at `path` if not already present.

    This does NOT screen the symbol for sharia compliance -- see the
    disclaimer header ShariaFilter's own whitelist.txt carries. Returns
    False without writing if the symbol (case-insensitive) is already on
    the list. Raises ValueError for text that isn't a plausible ticker
    (letters/digits/dot/hyphen only, e.g. "AAPL", "MPE.L", "BRK-B").
    """
    symbol = symbol.strip().upper()
    if not symbol or not _TICKER_RE.match(symbol):
        raise ValueError(f"invalid ticker symbol: {symbol!r}")

    with open(path, encoding="utf-8") as f:
        existing = {
            line.strip() for line in f if line.strip() and not line.strip().startswith("#")
        }

    if symbol in existing:
        return False

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{symbol}\n")

    return True


def remove_from_whitelist(path: str, symbol: str) -> bool:
    """Remove `symbol` from the whitelist file at `path` if present
    (case-insensitive). All other lines, including comments and blanks,
    are preserved in order. Returns False, leaving the file untouched, if
    no matching ticker line is found.
    """
    symbol = symbol.strip().upper()

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    kept = []
    removed = False
    for line in lines:
        stripped = line.strip()
        is_match = (
            not removed
            and stripped
            and not stripped.startswith("#")
            and stripped.upper() == symbol
        )
        if is_match:
            removed = True
            continue
        kept.append(line)

    if not removed:
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)

    return True


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
