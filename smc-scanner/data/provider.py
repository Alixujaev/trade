"""Data provayderlar uchun mavhum (abstract) interfeys."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class DataProvider(ABC):
    """Barcha data provayderlar shu interfeysga amal qilishi kerak.

    Bugun yfinance, ertaga Alpaca/IBKR — provayder almashsa ham,
    shu interfeysga tayanuvchi qolgan kod o'zgarmaydi.
    """

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        *,
        use_cache: bool = True,
        include_extended_hours: bool = False,
        closed_only: bool = False,
        as_of: datetime | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """OHLCV ma'lumotlarini standart formatda qaytaradi.

        Qaytadigan DataFrame: index — tz-aware (UTC) DatetimeIndex, nomi
        "datetime", o'sish tartibida; columns — ['open','high','low','close','volume'].

        Parameters
        ----------
        symbol : str
            Aksiya/ETF belgisi (masalan 'AAPL', 'SPUS').
        interval : str
            Bar intervali ('1d', '1wk', '1h', '4h', '5m', '15m').
        use_cache : bool, optional
            Keshdan o'qish/keshga yozish (standart: True).
        include_extended_hours : bool, optional
            Premarket va postmarket ma'lumotlarini qo'shish (standart: False — faqat RTH).
        closed_only : bool, optional
            Faqat yopilgan barlarni qaytarish, shakllanayotgan barni chiqarib tashlash (standart: False).
        as_of : datetime | None, optional
            Closed bar tekshiruvi uchun vaqt nuqtasi (None bo'lsa joriy UTC vaqti).
        """
        raise NotImplementedError
