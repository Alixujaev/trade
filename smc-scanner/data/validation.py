"""OHLCV ma'lumotlarining sifatini va strukturaviy yaxlitligini tekshirish moduli.

Qoidalar:
1. Kerakli ustunlar: 'open', 'high', 'low', 'close', 'volume' mavjud bo'lishi shart.
2. Barcha qiymatlar sonli (numeric) bo'lishi va NaN qatorlar tashlanishi shart.
3. Timestamp'lar vaqt bo'yicha o'sish tartibida (sorted ascending) va takrorlanmas bo'lishi shart.
4. Salbiy hajm (negative volume) bo'lmasligi shart (volume >= 0).
5. Mantiqiy OHLC chegaralari:
   - high >= low
   - high >= open
   - high >= close
   - low <= open
   - low <= close
   Buzilgan qatorlar (malformed rows) filtrlanadi.
6. Sun'iy ma'lumot to'qilmaydi.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS: list[str] = ["open", "high", "low", "close", "volume"]


def validate_ohlcv(df: pd.DataFrame, *, symbol: str = "") -> pd.DataFrame:
    """OHLCV DataFrame sifatini tekshiradi va tozalangan nusxasini qaytaradi.

    Parameters
    ----------
    df : pd.DataFrame
        Tekshiriladigan xom yoki qisman tozalangan DataFrame.
    symbol : str, optional
        Xatolik xabarlarida ko'rsatiladigan aksiya belgisi.

    Returns
    -------
    pd.DataFrame
        Standartlashtirilgan, tartiblangan, barcha qoidalarga javob beradigan DataFrame.

    Raises
    ------
    ValueError
        Kerakli ustunlar yo'q bo'lsa, data bo'sh bo'lsa yoki barcha qatorlar yaroqsiz bo'lsa.
    """
    if df is None or df.empty:
        raise ValueError(f"{symbol or 'DataFrame'} uchun ma'lumot bo'sh")

    # Ustun nomlarini kichik harfga keltirish
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{symbol} uchun kerakli ustunlar yo'q: {missing}")

    df = df[REQUIRED_COLUMNS]

    # Sonli formatga o'tkazish
    for col in REQUIRED_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # NaN larni tashlash
    df = df.dropna()

    # Index datetime ekanligini ta'minlash
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # Timezone: agar naive bo'lsa UTC deb belgilanadi, aks holda UTC ga o'tkaziladi
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "datetime"

    # Dublikat timestamp'lardan oxirgisini saqlash
    df = df[~df.index.duplicated(keep="last")]

    # Tartiblash
    df = df.sort_index()

    # Mantiqiy OHLC munosabatlari va manfiy hajmni tekshirish
    valid_mask = (
        (df["volume"] >= 0)
        & (df["high"] >= df["low"])
        & (df["high"] >= df["open"])
        & (df["high"] >= df["close"])
        & (df["low"] <= df["open"])
        & (df["low"] <= df["close"])
    )
    clean_df = df.loc[valid_mask]

    if clean_df.empty:
        raise ValueError(
            f"{symbol or 'DataFrame'} uchun barcha qatorlar yaroqsiz (malformed/invalid OHLCV)"
        )

    return clean_df
