from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Strategy(ABC):
    name: str

    @abstractmethod
    def target_position(self, df: pd.DataFrame) -> pd.Series:
        """Return a 0/1 target position Series aligned to df.index.

        Must only use data up to and including each row's own bar (INV-1).
        """
        raise NotImplementedError


def _hold_between(entries: pd.Series, exits: pd.Series) -> pd.Series:
    signal = pd.Series(np.nan, index=entries.index)
    signal[exits] = 0
    signal[entries] = 1  # entries take priority over exits on the same bar
    return signal.ffill().fillna(0).astype(int)
