"""Data provayderlar uchun mavhum (abstract) interfeys."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """Barcha data provayderlar shu interfeysga amal qilishi kerak.

    Bugun yfinance, ertaga Alpaca/IBKR — provayder almashsa ham,
    shu interfeysga tayanuvchi qolgan kod o'zgarmaydi.
    """

    @abstractmethod
    def get_ohlcv(self, symbol: str, interval: str, *, use_cache: bool = True) -> pd.DataFrame:
        """OHLCV ma'lumotlarini standart formatda qaytaradi.

        Qaytadigan DataFrame: index — tz-aware (UTC) DatetimeIndex, nomi
        "datetime", o'sish tartibida; columns — ['open','high','low','close','volume'].
        """
        raise NotImplementedError
