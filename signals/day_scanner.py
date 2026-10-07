"""signals/day_scanner.py: Day trading skaneri va non-directive signal formatter.

METODOLOGIK QOIDA:
- Bu modul to'g'ridan-to'g'ri trading buyrug'i (BUY/SELL) bermaydi.
- Faqatgina bozor holatini, SMC kontekstini, VWAP va hajm dalillarini ko'rsatadi.
- Hech qanday "BUY NOW", "ENTER LONG", "STRONG BUY", "BUY SIGNAL" kabi direktiv
  iboralar ishlatilmaydi.
- Forming (tugallanmagan) barlar ishlatilmaydi (`closed_only=True`).
- Qat'iy no-lookahead: barcha hisob-kitoblar `as_of` vaqtida yopilgan barlarga asoslanadi.
"""

from __future__ import annotations

from datetime import datetime
import math
import pandas as pd

from data.factory import get_provider
from data.provider import DataProvider
from strategy.day.types import DaySetup, DaySetupStatus
from strategy.day.vwap_momentum import evaluate_vwap_momentum


def scan_day(
    symbol: str,
    *,
    provider: DataProvider | None = None,
    as_of: datetime | pd.Timestamp | None = None,
    include_extended_hours: bool = True,
) -> DaySetup:
    """Belgilangan ticker bo'yicha Day Trading (DAY-01 VWAP Momentum) holatini skanerlaydi.

    Parameters
    ----------
    symbol : str
        Aksiya belgisi (masalan 'AAPL').
    provider : DataProvider | None, optional
        Bozor ma'lumotlari provayderi. None bo'lsa default provayder olinadi.
    as_of : datetime | pd.Timestamp | None, optional
        Point-in-time tekshiruv vaqti (backtest va simulyatsiyalar uchun juda muhim).
    include_extended_hours : bool, optional
        Premarket darajalarini (PMH/PML) hisoblash uchun extended hours ma'lumotlarini olish.

    Returns
    -------
    DaySetup
        Non-directive tahlil natijasi.
    """
    prov = provider or get_provider()

    # 1. 5m RTH barlarini olish (faqat yopilgan barlar)
    try:
        df_5m = prov.get_ohlcv(
            symbol,
            "5m",
            include_extended_hours=False,
            closed_only=True,
            as_of=as_of,
        )
    except Exception as exc:
        now_ts = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now()
        return DaySetup(
            symbol=symbol,
            timestamp=now_ts,
            timeframe="5m",
            status=DaySetupStatus.DATA_INSUFFICIENT,
            warnings=(f"5m data fetch failed: {exc}",),
        )

    # 2. 15m MTF kontekst barlarini olish
    df_15m: pd.DataFrame | None = None
    try:
        df_15m = prov.get_ohlcv(
            symbol,
            "15m",
            include_extended_hours=False,
            closed_only=True,
            as_of=as_of,
        )
    except Exception:
        df_15m = None

    # 3. Agar extended hours so'ralgan bo'lsa, intraday darajalar (PMH/PML) uchun olish
    df_ext: pd.DataFrame | None = None
    if include_extended_hours:
        try:
            df_ext = prov.get_ohlcv(
                symbol,
                "5m",
                include_extended_hours=True,
                closed_only=True,
                as_of=as_of,
            )
        except Exception:
            df_ext = None

    # 4. VWAP Momentum holatini baholash
    return evaluate_vwap_momentum(
        symbol=symbol,
        df_5m=df_5m,
        df_15m=df_15m,
        df_extended_5m=df_ext,
        as_of=as_of,
    )


def format_day_setup(setup: DaySetup) -> str:
    """DaySetup obyektini toza, non-directive matn shakliga keltiradi.

    QAT'IY QOIDA: Bu matn hech qachon BUY NOW, ENTER LONG yoki STRONG BUY
    kabi tavsiyalarni o'z ichiga olmaydi.
    """
    price_str = f"{setup.price:.2f}" if setup.is_valid_price() else "N/A"
    vwap_str = f"{setup.vwap:.2f}" if setup.is_valid_vwap() else "N/A"
    rsi_str = f"{setup.rsi:.1f}" if setup.is_valid_rsi() else "N/A"
    rvol_str = f"{setup.rvol:.1f}x" if setup.is_valid_rvol() else "N/A"

    lines = [
        "DAY SETUP",
        f"Symbol: {setup.symbol}",
        f"Timeframe: {setup.timeframe}",
        f"Status: {setup.status.value}",
        "",
        "Setup:",
        f"{setup.setup_type.replace('_', ' ')}",
        "",
        "Context:",
        f"- Observed price: {price_str}",
        f"- VWAP: {vwap_str} ({setup.vwap_relation.value})",
        f"- RSI(14): {rsi_str}",
        f"- RVOL: {rvol_str}",
        f"- 15m structure: {setup.structure_15m}",
        f"- 5m trigger: {setup.trigger}",
        "",
        f"Evidence: ({setup.evidence_score}/{setup.max_score})",
    ]

    if setup.evidence:
        for item in setup.evidence:
            lines.append(f"✓ {item}")
    else:
        lines.append("- None")

    if setup.warnings:
        lines.append("")
        lines.append("Context warnings:")
        for warning in setup.warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines)
