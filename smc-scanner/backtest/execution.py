"""backtest/execution.py: Intraday pozitsiya execution simulyatori.

METODOLOGIK QOIDA:
- Entry modeli: signal bari T yopilgach, T+1 bari OPEN narxida amalga oshiriladi.
- Stop / Target: DAY-01 da stop/target qoidalari aniqlanmagan, shuning uchun
  har qanday stop/target parametri BACKTEST ASSUMPTION deb belgilanadi.
- Forced exit: Har qanday ochiq pozitsiya 15:55 ET dagi bar CLOSE narxida majburiy yopiladi.
- Same-bar ambiguity: Bitta barda High>=TP va Low<=SL bo'lsa, konservativ
  ravishda "STOP FIRST" qoidasi qo'llanadi va ambiguitiy hisoblagichiga yoziladi.
"""

from __future__ import annotations

from typing import NamedTuple
import pandas as pd

from backtest.day_types import DayBacktestTrade, ExecutionConfig
from data.session import get_session_date, to_eastern
from strategy.day.types import DaySetup


class ExecutionSimulation(NamedTuple):
    """Bitta savdo simulyatsiyasi natijasi va uning tugash indeksi."""

    trade: DayBacktestTrade
    exit_bar_index: int
    was_ambiguous: bool


def simulate_trade_execution(
    df: pd.DataFrame,
    setup_bar_idx: int,
    setup: DaySetup,
    config: ExecutionConfig,
    *,
    vwap_series: pd.Series | None = None,
) -> ExecutionSimulation | None:
    """Signal baridan keyingi barlar bo'ylab pozitsiyani simulyatsiya qiladi.

    Parameters
    ----------
    df : pd.DataFrame
        5m OHLCV ma'lumotlari.
    setup_bar_idx : int
        Signal aniqlangan bar indeksi (T).
    setup : DaySetup
        DAY-01 setup obyekt.
    config : ExecutionConfig
        Execution parametrlari.
    vwap_series : pd.Series | None, optional
        VWAP qiymatlari seriyasi.

    Returns
    -------
    ExecutionSimulation | None
        Agar keyingi bar mavjud bo'lmasa yoki sessiya tugagan bo'lsa None.
    """
    n = len(df)
    entry_idx = setup_bar_idx + 1

    # 1. Keyingi bar mavjudligini tekshirish
    if entry_idx >= n:
        return None

    setup_time = df.index[setup_bar_idx]
    entry_time = df.index[entry_idx]

    # Sessiya o'zgargan bo'lsa (kun oxiridagi signal), yangi kunga o'tmaymiz
    if get_session_date(entry_time) != get_session_date(setup_time):
        return None

    # 2. Kirish narxini aniqlash (next bar OPEN)
    raw_entry = float(df["open"].iloc[entry_idx])
    slippage_mult = 1.0 + (config.slippage_bps / 10000.0)
    effective_entry = raw_entry * slippage_mult + config.commission_per_share

    # 3. Stop va Target narxlarini aniqlash (BACKTEST ASSUMPTION)
    stop_price: float | None = None
    risk_per_share: float | None = None

    if config.stop_mode == "SIGNAL_LOW":
        signal_low = float(df["low"].iloc[setup_bar_idx])
        if signal_low < raw_entry:
            stop_price = signal_low
            risk_per_share = raw_entry - stop_price
        else:
            # Agar signal low entry'dan past bo'lmasa fallback VWAP yoki 1%
            if setup.is_valid_vwap() and setup.vwap < raw_entry:
                stop_price = setup.vwap
                risk_per_share = raw_entry - stop_price
            else:
                stop_price = raw_entry * 0.99
                risk_per_share = raw_entry - stop_price
    elif config.stop_mode == "VWAP":
        if setup.is_valid_vwap() and setup.vwap < raw_entry:
            stop_price = setup.vwap
            risk_per_share = raw_entry - stop_price
        else:
            stop_price = raw_entry * 0.99
            risk_per_share = raw_entry - stop_price

    target_price: float | None = None
    if (
        config.target_multiple is not None
        and risk_per_share is not None
        and risk_per_share > 0.0
    ):
        target_price = raw_entry + config.target_multiple * risk_per_share

    # 4. Pozitsiyani entry_idx dan boshlab har bir bar bo'ylab kuzatish
    exit_idx: int = entry_idx
    exit_time: pd.Timestamp = entry_time
    raw_exit: float = raw_entry
    exit_reason: str = "end_of_data"
    was_ambiguous: bool = False

    session_date = get_session_date(entry_time)

    for j in range(entry_idx, n):
        bar_ts = df.index[j]
        curr_session = get_session_date(bar_ts)

        # Kun almashib qolgan bo'lsa (favqulodda holat, majburiy chiqish)
        if curr_session != session_date:
            exit_idx = j - 1
            exit_time = df.index[exit_idx]
            raw_exit = float(df["close"].iloc[exit_idx])
            exit_reason = "forced_eod"
            break

        bar_time_et = to_eastern(pd.DatetimeIndex([bar_ts]))[0]
        bar_high = float(df["high"].iloc[j])
        bar_low = float(df["low"].iloc[j])
        bar_close = float(df["close"].iloc[j])

        # 4a. Majburiy kunlik yopilish (15:55 ET)
        if bar_time_et.time() >= config.force_exit_time:
            exit_idx = j
            exit_time = bar_ts
            raw_exit = bar_close
            exit_reason = "forced_eod"
            break

        # 4b. Stop va Target tekshiruvi
        hit_target = target_price is not None and bar_high >= target_price
        hit_stop = stop_price is not None and bar_low <= stop_price

        if hit_target and hit_stop:
            # SAME-BAR AMBIGUITY!
            was_ambiguous = True
            exit_idx = j
            exit_time = bar_ts
            if config.same_bar_rule == "STOP_FIRST":
                raw_exit = stop_price  # type: ignore[assignment]
                exit_reason = "stop"
            else:
                raw_exit = target_price  # type: ignore[assignment]
                exit_reason = "target"
            break

        if hit_stop:
            exit_idx = j
            exit_time = bar_ts
            raw_exit = stop_price  # type: ignore[assignment]
            exit_reason = "stop"
            break

        if hit_target:
            exit_idx = j
            exit_time = bar_ts
            raw_exit = target_price  # type: ignore[assignment]
            exit_reason = "target"
            break

        # 4c. VWAP kesishib pastga tushganda chiqish (ixtiyoriy)
        if config.exit_on_vwap_cross and vwap_series is not None:
            curr_vwap = vwap_series.iloc[j]
            if not pd.isna(curr_vwap) and bar_close < curr_vwap:
                exit_idx = j
                exit_time = bar_ts
                raw_exit = bar_close
                exit_reason = "vwap_loss"
                break

        # 4d. Maksimal ushlab turish vaqti
        hold_mins = int((bar_ts - entry_time).total_seconds() / 60)
        if hold_mins >= config.max_holding_minutes:
            exit_idx = j
            exit_time = bar_ts
            raw_exit = bar_close
            exit_reason = "max_time"
            break
    else:
        # Ma'lumot tugadi
        exit_idx = n - 1
        exit_time = df.index[exit_idx]
        raw_exit = float(df["close"].iloc[exit_idx])
        exit_reason = "end_of_data"

    # Chiqish narxi va xarajatlar
    exit_slip_mult = 1.0 - (config.slippage_bps / 10000.0)
    effective_exit = raw_exit * exit_slip_mult - config.commission_per_share

    gross_return = (raw_exit - raw_entry) / raw_entry
    net_return = (effective_exit - effective_entry) / effective_entry

    r_multiple = (
        (raw_exit - raw_entry) / risk_per_share
        if risk_per_share is not None and risk_per_share > 0
        else None
    )

    trade = DayBacktestTrade(
        symbol=setup.symbol,
        setup_time=setup_time,
        entry_time=entry_time,
        entry_price=effective_entry,
        exit_time=exit_time,
        exit_price=effective_exit,
        exit_reason=exit_reason,
        stop_price=stop_price,
        target_price=target_price,
        gross_return=gross_return,
        net_return=net_return,
        risk_per_share=risk_per_share,
        r_multiple=r_multiple,
        rsi_at_setup=setup.rsi,
        rvol_at_setup=setup.rvol,
        vwap_at_setup=setup.vwap,
        structure_5m=setup.structure_5m,
        structure_15m=setup.structure_15m,
        evidence=setup.evidence,
        warnings=setup.warnings,
        hold_duration_minutes=int((exit_time - entry_time).total_seconds() / 60),
        trigger_type=setup.trigger,
        vwap_relation=(
            setup.vwap_relation.value
            if hasattr(setup.vwap_relation, "value")
            else str(setup.vwap_relation)
        ),
        setup_status=(
            setup.status.value
            if hasattr(setup.status, "value")
            else str(setup.status)
        ),
        observed_price_at_setup=setup.price,
    )

    return ExecutionSimulation(
        trade=trade,
        exit_bar_index=exit_idx,
        was_ambiguous=was_ambiguous,
    )
