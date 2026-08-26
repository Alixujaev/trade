"""Minimal backtest simulyator: signal'lar ro'yxatini kapital/pozitsiya bilan simulyatsiya qiladi.

Qoidalar (barchasi ataylab soddalashtirilgan — "chiroyli emas, o'lchanadigan"):
- Bir vaqtda FAQAT 1 ochiq pozitsiya. Bu yerda amalga oshiriladi (signal.py'da EMAS —
  chunki faqat shu funksiya savdo natijalarini simulyatsiya qilgani uchun "ochiq
  pozitsiya" nima ekanini biladi; signal.py'ni qarang).
- Har signal uchun stop/target kuzatuvi ENTRY BARIDAN emas, `entry_index_pos + 1`dan
  boshlanadi — entry shu barning ichida sodir bo'lgan deb faraz qilinadi, keyingi
  xavf keyingi bardan boshlab kuzatiladi (intra-bar tartibni OHLC'dan bilib bo'lmaydi,
  shuning uchun bu konvensiya smc/zones.py'ning o'z fill-skan konvensiyasiga mos).
- Bir barda HAM stop HAM target'ga tegilsa: KONSERVATIV — stop birinchi tegdi deb
  hisoblanadi (pessimistik, real natijani bo'rttirmaslik uchun).
- exit_mode="fixed": stop + keyingi swing high target (mavjud, standart). "trailing":
  fixed target YO'Q, stop ATR asosida yuqoriga suriladi — _simulate_trailing_exit'ga qarang.
- Position sizing: "fixed_pct" — risk_pct*capital / (entry-stop). "atr" — xuddi
  shu risk miqdori, lekin bir aksiya uchun xavf ATR bilan normallashtiriladi
  (solishtirish uchun — bir xil savdolar, boshqa o'lcham falsafasi).
- Kapital yetmasa (shares*entry > capital): pozitsiya CAPITAL/ENTRY'gacha KICHRAYTIRILADI
  (o'tkazib yuborilmaydi) — spot/leveragesiz, "qo'lingdan kelganicha ol" mantig'i.
- Kapital <= 0 bo'lib qolsa: yangi savdolar butunlay to'xtatiladi.
- R-multiple FAQAT narxlardan hisoblanadi (shares/komissiya/slippage ta'sir qilmaydi) —
  standart amaliyot: stop-out doim aniq -1.0R, trade xarajatlari faqat dollar PnL'ga ta'sir qiladi.
  R-multiple exit_mode'dan qat'iy nazar DOIM entry'dagi ORIGINAL stop masofasidan
  hisoblanadi — trailing stop qayerga borishidan qat'iy nazar (R "rejalashtirilgan xavf
  ko'paytmasi" ma'nosini yo'qotmasligi kerak).
"""

from __future__ import annotations

import pandas as pd

from backtest.metrics import (
    avg_hold_days,
    avg_r_multiple,
    buy_and_hold_return_pct,
    expectancy_r,
    max_drawdown_pct,
    profit_factor,
    win_rate,
)
from backtest.types import BacktestResult, TradeResult
from config.settings import ATR_PERIOD, ATR_RISK_MULT, TRAIL_ATR_MULT
from smc.types import TradeSetup
from smc.zones import compute_atr


def _simulate_fixed_exit(
    df: pd.DataFrame,
    signal: TradeSetup,
    closes,
    highs,
    lows,
    n: int,
) -> tuple[int, float, str, float, float]:
    """Mavjud (fixed) chiqish mantig'i — stop yoki keyingi swing-high target.

    Qaytaradi: (exit_index_pos, exit_price, exit_reason, min_low, mfe_r_running_high_component).
    Oxirgi qiymat — bu funksiya `running_high`ning O'ZINI emas, uni chaqiruvchi
    mfe_r'ga aylantirishi uchun xom `running_high`ni qaytaradi (run_backtest'da mfe_r
    hisoblanadi, actual_risk ikkala exit funksiyasida ham bir xil formula bo'lgani uchun).
    """
    exit_index_pos: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    min_low = signal.entry_price
    running_high = signal.entry_price

    for j in range(signal.entry_index_pos + 1, n):
        min_low = min(min_low, float(lows[j]))
        running_high = max(running_high, float(highs[j]))
        hit_stop = lows[j] <= signal.stop_price
        hit_target = highs[j] >= signal.target_price
        if hit_stop:  # ikkalasi ham teksa - konservativ: stop g'olib
            exit_index_pos, exit_price, exit_reason = j, signal.stop_price, "stop"
            break
        if hit_target:
            exit_index_pos, exit_price, exit_reason = j, signal.target_price, "target"
            break

    if exit_index_pos is None:
        # Ma'lumot tugadi — hali ochiq pozitsiyani oxirgi close bilan yopamiz.
        # min_low/running_high yuqoridagi tsiklda allaqachon to'liq hisoblangan (hit
        # bo'lmagani uchun tsikl to'liq oxirigacha yurgan), qayta hisoblash shart emas.
        exit_index_pos = n - 1
        exit_price = float(closes[-1])
        exit_reason = "end_of_data"

    return exit_index_pos, exit_price, exit_reason, min_low, running_high


def _simulate_trailing_exit(
    df: pd.DataFrame,
    signal: TradeSetup,
    atr: pd.Series,
    closes,
    highs,
    lows,
    n: int,
    trail_atr_mult: float,
) -> tuple[int, float, str, float, float]:
    """ATR-asosida trailing stop (sodda variant — swing-low-asosli EMAS, chunki bu
    savdo davomida yangi tasdiqlangan swing'larni kuzatishni talab qilardi — ortiqcha
    murakkablik). Stop hech qachon pastga tushmaydi. Fixed target ISHLATILMAYDI —
    trend cho'zilishiga imkon beriladi.

    MUHIM (konservativ tanlov, stop/target tie-break bilan bir oilada): har bar
    AVVAL oldingi (bar j-1 orqali o'rnatilgan) stop bilan tekshiriladi, SO'NG shu
    barning o'zi yangi stop'ni ko'taradi (keyingi bar uchun). Bitta barda ham eski
    stop buzilib ham yangi (yuqoriroq) stop hosil bo'lishi mumkin bo'lgan holatda —
    HAR DOIM eski (pastroq) narxda chiqiladi, hech qachon yangi ko'targan darajada
    emas. Bu ataylab pessimistik: natijani bo'rttirmaslik uchun (real vaqtda intra-bar
    tartibni OHLC'dan bilib bo'lmaydi).

    Lookahead yo'q: `atr.iloc[j]` faqat bar j (va undan oldingi)ga tegishli ma'lumot
    bilan hisoblangan (compute_atr — orqaga qarovchi rolling oyna), `highs[j]`/`lows[j]`
    esa shu barning o'z (allaqachon yopilgan) qiymatlari.
    """
    current_stop = signal.stop_price
    running_high = signal.entry_price
    min_low = signal.entry_price
    exit_index_pos: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None

    for j in range(signal.entry_index_pos + 1, n):
        min_low = min(min_low, float(lows[j]))

        if lows[j] <= current_stop:
            exit_index_pos, exit_price, exit_reason = j, current_stop, "trailing_stop"
            break

        if highs[j] > running_high:
            running_high = float(highs[j])
            atr_j = atr.iloc[j]
            if not pd.isna(atr_j):  # ATR hali warmup'da (NaN) — shu bar stop o'zgarmaydi (xavfsiz no-op)
                candidate_stop = running_high - trail_atr_mult * float(atr_j)
                current_stop = max(current_stop, candidate_stop)  # hech qachon pastga tushmaydi

    if exit_index_pos is None:
        exit_index_pos = n - 1
        exit_price = float(closes[-1])
        exit_reason = "end_of_data"

    return exit_index_pos, exit_price, exit_reason, min_low, running_high


def run_backtest(
    df: pd.DataFrame,
    signals: list[TradeSetup],
    *,
    initial_capital: float = 10_000,
    risk_model: str = "fixed_pct",
    risk_pct: float = 0.01,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
    atr_period: int = ATR_PERIOD,
    exit_mode: str = "fixed",
    trail_atr_mult: float = TRAIL_ATR_MULT,
) -> BacktestResult:
    """Signal'larni xronologik simulyatsiya qilib, savdo natijalari va metrikalarni qaytaradi.

    exit_mode="atr" bilan risk_model="atr" birga ishlatilsa, ikkalasi ham BIR XIL
    atr/atr_period'dan foydalanadi — bu ataylab shunday (bitta ATR seriyasi,
    ikki xil maqsad uchun: pozitsiya o'lchami va trailing stop masofasi).
    """
    if risk_model not in ("fixed_pct", "atr"):
        raise ValueError(f"Noto'g'ri risk_model: {risk_model!r}. Ruxsat etilganlar: fixed_pct, atr")
    if exit_mode not in ("fixed", "trailing"):
        raise ValueError(f"Noto'g'ri exit_mode: {exit_mode!r}. Ruxsat etilganlar: fixed, trailing")

    signals_sorted = sorted(signals, key=lambda s: s.entry_index_pos)
    atr = compute_atr(df, atr_period)
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)

    capital = initial_capital
    next_available_index_pos = 0
    trades: list[TradeResult] = []
    equity_curve: list[float] = [initial_capital]

    for signal in signals_sorted:
        if capital <= 0:
            break  # kapital tugadi — yangi savdo yo'q
        if signal.entry_index_pos < next_available_index_pos:
            continue  # pozitsiya hali ochiq (yoki xuddi shu barda qayta kirish)

        entry_price = signal.entry_price
        stop_price = signal.stop_price

        risk_amount = risk_pct * capital
        if risk_model == "fixed_pct":
            per_share_risk = entry_price - stop_price
        else:  # "atr"
            atr_entry = atr.iloc[signal.entry_index_pos]
            per_share_risk = (
                ATR_RISK_MULT * float(atr_entry)
                if not pd.isna(atr_entry)
                else entry_price - stop_price  # ATR hali yo'q (warmup) — fixed_pct masofasiga qaytamiz
            )

        if per_share_risk <= 0:
            continue  # noto'g'ri/degenerativ setup — o'tkazib yuboriladi
        shares = risk_amount / per_share_risk

        if shares * entry_price > capital:
            shares = capital / entry_price  # pozitsiya kapitalga moslab kichraytiriladi

        if shares <= 0:
            continue

        if exit_mode == "fixed":
            exit_index_pos, exit_price, exit_reason, min_low, running_high = _simulate_fixed_exit(
                df, signal, closes, highs, lows, n
            )
        else:  # "trailing"
            exit_index_pos, exit_price, exit_reason, min_low, running_high = _simulate_trailing_exit(
                df, signal, atr, closes, highs, lows, n, trail_atr_mult
            )

        effective_entry = entry_price * (1 + slippage_pct)
        effective_exit = exit_price * (1 - slippage_pct)
        gross_pnl = shares * (effective_exit - effective_entry)
        commission = commission_pct * shares * (effective_entry + effective_exit)
        pnl = gross_pnl - commission

        # R-multiple/MAE/MFE DOIM narx (entry-stop) masofasidan hisoblanadi — risk_model
        # va exit_mode'dan qat'iy nazar (ATR sizing/trailing faqat shares/chiqish
        # narxiga ta'sir qiladi, R-multiple ta'rifiga emas — stop-out doim aniq -1.0R).
        actual_risk = entry_price - stop_price
        r_multiple = (exit_price - entry_price) / actual_risk
        mae_r = (entry_price - min_low) / actual_risk
        mfe_r = (running_high - entry_price) / actual_risk

        exit_ts = df.index[exit_index_pos]
        hold_duration_days = (exit_ts - signal.entry_ts).total_seconds() / 86400

        trades.append(
            TradeResult(
                entry_ts=signal.entry_ts,
                exit_ts=exit_ts,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_index_pos=signal.entry_index_pos,
                exit_index_pos=exit_index_pos,
                shares=shares,
                exit_reason=exit_reason,
                r_multiple=r_multiple,
                pnl=pnl,
                hold_duration_days=hold_duration_days,
                mae_r=mae_r,
                mfe_r=mfe_r,
            )
        )

        capital += pnl
        equity_curve.append(capital)
        next_available_index_pos = exit_index_pos + 1

    metrics = {
        "num_trades": len(trades),
        "win_rate": win_rate(trades),
        "avg_r_multiple": avg_r_multiple(trades),
        "expectancy_r": expectancy_r(trades),
        "profit_factor": profit_factor(trades),
        "total_return_pct": (capital - initial_capital) / initial_capital * 100 if initial_capital > 0 else 0.0,
        "max_drawdown_pct": max_drawdown_pct(equity_curve),
        "avg_hold_days": avg_hold_days(trades),
        "buy_hold_return_pct": buy_and_hold_return_pct(df),
    }

    return BacktestResult(
        trades=trades,
        initial_capital=initial_capital,
        final_capital=capital,
        metrics=metrics,
    )
