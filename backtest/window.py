"""Backtest uchun sana oralig'i bo'yicha data kesish."""

from __future__ import annotations

import pandas as pd


def slice_date_range(df: pd.DataFrame, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    """df'ni [start_date, end_date] oralig'iga kesadi (ikkalasi ham inklyuziv, ikkalasi ham ixtiyoriy).

    MUHIM (lookahead): bu funksiya faqat XOM DATA'ni kesadi — struktura/signal
    HALI hisoblanmagan. Kesilgan natija keyin generate_signals'ga uzatiladi, shuning
    uchun swing/BOS-CHoCH/zona BARCHASI shu oyna ichidagi barlardan NOLDAN quriladi;
    oyna tashqarisidagi (undan oldingi yoki keyingi) hech qanday ma'lumot signal
    logikasiga sizib kirmaydi. Buni har doim generate_signals'dan OLDIN chaqiring —
    to'liq tarixda hisoblangan natijalarni KEYIN filtrlash lookahead yaratadi
    (struktura oyna tashqarisidagi trenddan "meros" bo'lib qoladi).
    """
    result = df
    if start_date is not None:
        result = result[result.index >= pd.Timestamp(start_date, tz="UTC")]
    if end_date is not None:
        result = result[result.index <= pd.Timestamp(end_date, tz="UTC")]
    return result
