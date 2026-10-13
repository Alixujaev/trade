"""scripts/backtest_orb.py: ORB backtest CLI (owner ruxsati bilan ishga tushiriladi).

    # faqat lokal cache, tarmoq bloklangan, artefaktlar bilan:
    python scripts/backtest_orb.py --start 2026-07-02 --end 2026-09-25 --capital 100000 \
        --earnings config/earnings_calendar.csv --cache-dir data/cache --out artifacts/orb/smoke_test

    # provayder orqali (tarmoqdan data olishi mumkin):
    python scripts/backtest_orb.py --start ... --end ... --capital ... --earnings ...

--cache-dir: <dir>/<SYMBOL>_5m.parquet read-only o'qiladi, provayder yaratilmaydi; ishlash davomida har qanday
socket ulanishi xato beradi (yangi download yoki fallback yo'q). Earnings CSV yo'q yoki oraliqni qamrab olmasa -
fail closed (data/earnings.py). Strategiya, risk va ijro kodi: backtest/orb_engine.run_orb_backtest (o'zgarmagan).
Metrika uchun data yetarli bo'lmasa "N/A" (sabab bilan), hech qachon 0 deb taxmin qilinmaydi.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import date, timedelta
import json
import math
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from backtest.orb_engine import load_bars, run_orb_backtest  # noqa: E402
from config.day_universe import FROZEN_DAY_UNIVERSE  # noqa: E402
from data.earnings import load_earnings_calendar  # noqa: E402
from data.session import NY_TZ, get_session_dates, is_rth_series, to_eastern  # noqa: E402
from strategy.day.orb_rules import OrbRules  # noqa: E402

OHLCV = ("open", "high", "low", "close", "volume")
NA = "N/A"


class NetworkBlocked(RuntimeError):
    pass


@contextmanager
def no_network():
    orig = socket.socket.connect, socket.socket.connect_ex, socket.create_connection

    def refuse(*_a, **_k):
        raise NetworkBlocked("network access attempted during a --cache-dir run")
    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.create_connection = refuse
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = orig


def load_cache(cache_dir: Path, symbols: list[str]) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    bars, paths = {}, {}
    for s in symbols:
        p = cache_dir / f"{s}_5m.parquet"
        if not p.is_file():
            raise SystemExit(f"ABORT: cache file missing for {s}: {p}")
        df = pd.read_parquet(p)
        if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
            raise SystemExit(f"ABORT: {p} has no tz-aware DatetimeIndex")
        if [c for c in OHLCV if c not in df.columns]:
            raise SystemExit(f"ABORT: {p} lacks OHLCV columns")
        bars[s], paths[s] = df[list(OHLCV)].sort_index(), str(p)
    return bars, paths


def rth_sessions(df: pd.DataFrame) -> pd.Series:
    rth = df.loc[is_rth_series(df.index).to_numpy()]
    return get_session_dates(rth.index)


# ------------------------------------------------------------------ metrics

def series_metrics(equity: pd.Series, capital: float) -> dict:
    """equity: session-close equity indexed by session (excluding the start point)."""
    out: dict = {}
    n = len(equity)
    if n == 0:
        return {k: NA for k in ("net_return", "cagr", "max_drawdown", "sharpe", "sortino")} | {"reason": "no sessions"}
    path = pd.concat([pd.Series([capital]), equity.reset_index(drop=True)])
    rets = path.pct_change().dropna()
    out["net_return"] = float(path.iloc[-1] / capital - 1.0)
    out["cagr"] = float((path.iloc[-1] / capital) ** (252.0 / n) - 1.0)
    out["cagr_note"] = f"annualised from {n} sessions - not meaningful evidence"
    peak = path.cummax()
    out["max_drawdown"] = float(((path - peak) / peak).min())
    sd = rets.std(ddof=1) if len(rets) >= 2 else float("nan")
    out["sharpe"] = float(rets.mean() / sd * math.sqrt(252)) if len(rets) >= 2 and sd > 0 else NA
    downside = rets[rets < 0]
    dd = math.sqrt(float((rets.clip(upper=0) ** 2).mean())) if len(downside) else 0.0
    out["sortino"] = float(rets.mean() / dd * math.sqrt(252)) if len(rets) >= 2 and dd > 0 else NA
    if out["sharpe"] == NA:
        out["sharpe_reason"] = "fewer than 2 daily returns or zero volatility"
    if out["sortino"] == NA:
        out["sortino_reason"] = "no negative daily return (downside deviation 0) or fewer than 2 returns"
    return out


def equal_weight_bh(bars: dict[str, pd.DataFrame], sessions: list[date], rules: OrbRules) -> dict:
    first, last = sessions[0], sessions[-1]
    per = rules.initial_capital / len(bars)
    cash, holdings, legs = rules.initial_capital, {}, []
    for s, df in sorted(bars.items()):
        sd = rth_sessions(df)
        day0 = df.loc[sd.index[sd == first]]
        if day0.empty:
            return {"status": NA, "reason": f"{s} has no bars on {first}"}
        o = float(day0["open"].iloc[0])
        fill = rules.buy_fill(o)
        sh = math.floor(per / (fill + rules.commission_per_share))
        cash -= sh * (fill + rules.commission_per_share)
        holdings[s] = sh
        legs.append({"symbol": s, "shares": sh, "entry_open": o, "entry_fill": fill})
    marks = []
    for d in sessions:
        val = cash
        for s, df in bars.items():
            sd = rth_sessions(df)
            day = df.loc[sd.index[sd == d]]
            if day.empty:
                return {"status": NA, "reason": f"{s} has no bars on {d}"}
            px = float(day["close"].iloc[-1])
            if d == last:
                px = rules.sell_fill(px)
                val += holdings[s] * px - holdings[s] * rules.commission_per_share
            else:
                val += holdings[s] * px
        marks.append(val)
    eq = pd.Series(marks, index=sessions)
    return {"status": "OK", "method": "capital/25 per ticker, whole shares, buy first-session 09:30 open, "
            "sell last-session close; 5 bps slippage and $0.005/share commission on both legs; marked at closes",
            "final_equity": float(eq.iloc[-1]), **series_metrics(eq, rules.initial_capital), "legs": legs}


# ------------------------------------------------------------------ checks

def run_checks(trades: list[dict], skips: list[dict], earnings, symbols: list[str], start: date, end: date,
               sessions: list[date], rules: OrbRules) -> list[dict]:
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    ts = lambda x: pd.Timestamp(x)  # noqa: E731
    bad = [t for t in trades if not (start <= date.fromisoformat(t["session"]) <= end)]
    add("trade sessions within backtest range", not bad, f"{len(bad)} outside")
    keys = [(t["symbol"], t["session"]) for t in trades]
    add("no duplicate (symbol, session) trades", len(keys) == len(set(keys)), f"{len(keys) - len(set(keys))} duplicates")
    la = [t for t in trades if not (ts(t["entry_time"]) - ts(t["signal_time"]) == pd.Timedelta(minutes=5)
                                    and ts(t["signal_time"]) < ts(t["entry_time"]) <= ts(t["exit_time"]))]
    add("entry is the bar after the signal; entry <= exit (no lookahead)", not la, f"{len(la)} violations")
    same = [t for t in trades if to_eastern(ts(t["exit_time"])).date().isoformat() != t["session"]]
    add("exit in the same session (no overnight)", not same, f"{len(same)} violations")
    win = [t for t in trades if not (pd.Timestamp("09:45").time() <= to_eastern(ts(t["signal_time"])).time()
                                     < pd.Timestamp("11:00").time())]
    add("signal bar opens in 09:45-11:00 ET", not win, f"{len(win)} violations")
    geo = [t for t in trades if not (t["stop"] == t["or_low"] and abs(t["target"] - (t["entry_open"] + 2 * t["risk_per_share"])) < 1e-9)]
    add("stop = OR low, target = entry + 2R", not geo, f"{len(geo)} violations")
    per_day: dict[str, list[dict]] = {}
    for t in trades:
        per_day.setdefault(t["session"], []).append(t)
    add("<= 2 trades per day", all(len(v) <= rules.max_trades_per_day for v in per_day.values()),
        f"max {max((len(v) for v in per_day.values()), default=0)}")
    max_conc, cap_viol = 0, 0
    realised = rules.initial_capital
    for d in sorted(per_day):
        day = per_day[d]
        for t in day:
            t0 = ts(t["entry_time"])
            live = [u for u in day if ts(u["entry_time"]) <= t0 < ts(u["exit_time"]) or u is t]
            max_conc = max(max_conc, len(live))
            closed_before = sum(u["pnl"] for u in day if ts(u["exit_time"]) < t0)
            notional = sum(u["shares"] * (u["entry_fill"] + rules.commission_per_share) for u in live)
            if notional > realised + closed_before + 1e-6:
                cap_viol += 1
        realised += sum(u["pnl"] for u in day)
    add("<= 2 concurrent positions", max_conc <= rules.max_open_positions, f"max {max_conc}")
    add("concurrent notional <= available capital", cap_viol == 0, f"{cap_viol} violations")
    on_earn = [t for t in trades if earnings.is_earnings_day(t["symbol"], date.fromisoformat(t["session"]))]
    add("no trade on an earnings session", not on_earn, f"{len(on_earn)} violations")
    expected = {(s, d.isoformat()) for s in symbols for d in earnings.dates.get(s, ()) if d in set(sessions)}
    got = {(k["symbol"], k["session"]) for k in skips if k["reason"] == "earnings_day"}
    add("earnings skips == CSV sessions in range", got == expected,
        f"expected {len(expected)}, skipped {len(got)}, missing {sorted(expected - got)}, extra {sorted(got - expected)}")
    costs = [t for t in trades if not (abs(t["entry_fill"] - t["entry_open"] * (1 + rules.slippage_bps / 1e4)) < 1e-9
                                       and abs(t["exit_fill"] - t["exit_raw"] * (1 - rules.slippage_bps / 1e4)) < 1e-9)]
    add("5 bps slippage applied on both legs", not costs, f"{len(costs)} violations")
    pnl_bad = [t for t in trades if abs(t["pnl"] - ((t["exit_fill"] - t["entry_fill"]) * t["shares"]
                                                    - 2 * rules.commission_per_share * t["shares"])) > 1e-6]
    add("$0.005/share commission on both legs in P&L", not pnl_bad, f"{len(pnl_bad)} violations")
    return checks


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--capital", type=float, required=True)
    ap.add_argument("--earnings", required=True)
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--cache-dir", help="read <dir>/<SYMBOL>_5m.parquet only; network blocked; no provider")
    ap.add_argument("--out", help="artifact directory (must be empty or absent)")
    a = ap.parse_args(argv)
    start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    symbols = sorted(a.symbols or FROZEN_DAY_UNIVERSE)
    rules = OrbRules(initial_capital=a.capital)
    earnings = load_earnings_calendar(a.earnings)
    earnings.check_coverage(symbols, start, end)                     # fail closed before any data access
    out = Path(a.out) if a.out else None
    if out is not None and out.exists() and any(out.iterdir()):
        raise SystemExit(f"ABORT: output directory is not empty: {out}")

    if a.cache_dir:
        with no_network():
            bars, paths = load_cache(Path(a.cache_dir), symbols)
            res = run_orb_backtest(bars, rules, earnings, start, end)
    else:
        from data.factory import get_provider
        bars, paths = load_bars(get_provider(), symbols), {s: "provider" for s in symbols}
        res = run_orb_backtest(bars, rules, earnings, start, end)

    trades, skips, sessions = res.trades, res.skips, res.sessions
    data_cov = {}
    for s, df in bars.items():
        sd = sorted(d for d in set(rth_sessions(df)) if start <= d <= end)
        data_cov[s] = {"path": paths[s], "sessions": len(sd), "first": str(sd[0]) if sd else None,
                       "last": str(sd[-1]) if sd else None}
    used = sorted({t["symbol"] for t in trades})
    by_session: dict[str, float] = {}
    for t in trades:
        by_session[t["session"]] = by_session.get(t["session"], 0.0) + t["pnl"]
    eq_vals, run = [], a.capital
    for d in sessions:
        run += by_session.get(d.isoformat(), 0.0)
        eq_vals.append(run)
    equity = pd.Series(eq_vals, index=sessions)
    n = len(trades)
    exits = {r: sum(t["exit_reason"] == r for t in trades) for r in ("STOP", "TARGET", "FORCE_EXIT_1555", "SESSION_END")}
    skip_counts: dict[str, int] = {}
    for k in skips:
        skip_counts[k["reason"]] = skip_counts.get(k["reason"], 0) + 1
    commission = sum(2 * rules.commission_per_share * t["shares"] for t in trades)
    slippage = sum(t["shares"] * ((t["entry_fill"] - t["entry_open"]) + (t["exit_raw"] - t["exit_fill"])) for t in trades)
    metrics = {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "sessions": len(sessions),
                  "first_session": str(sessions[0]) if sessions else None, "last_session": str(sessions[-1]) if sessions else None},
        "universe": {"count": len(symbols), "symbols": symbols, "symbols_with_trades": used},
        "rules": rules.to_dict(),
        "trades": n,
        "win_rate": (sum(t["pnl"] > 0 for t in trades) / n) if n else NA,
        "total_pnl": sum(t["pnl"] for t in trades),
        "total_r": sum(t["r_multiple"] for t in trades) if n else NA,
        "avg_r": (sum(t["r_multiple"] for t in trades) / n) if n else NA,
        **series_metrics(equity, a.capital),
        "exits": exits,
        "costs": {"commission_total": commission, "slippage_total": slippage,
                  "note": "both included in every trade's P&L (entry_fill/exit_fill and 2 x $0.005/share)"},
        "skips": skip_counts,
        "earnings_skipped_symbol_sessions": skip_counts.get("earnings_day", 0),
        "benchmarks": {"equal_weight_buy_and_hold": equal_weight_bh(bars, sessions, rules) if sessions else
                       {"status": NA, "reason": "no sessions"},
                       "capital_constrained_buy_and_hold": {"status": NA, "reason":
                           "not defined comparably for an intraday strategy limited to 2 concurrent positions; "
                           "not computed rather than approximated"}},
        "inputs": {"earnings_calendar": str(Path(a.earnings)), "cache_dir": a.cache_dir,
                   "data": data_cov, "network": "blocked (socket connect refused)" if a.cache_dir else "provider"},
    }
    checks = run_checks(trades, skips, earnings, symbols, start, end, sessions, rules)
    metrics["checks"] = checks
    metrics["all_checks_passed"] = all(c["status"] == "PASS" for c in checks)

    summary = {k: metrics[k] for k in ("trades", "win_rate", "total_pnl", "net_return", "cagr", "max_drawdown",
                                       "sharpe", "sortino", "exits", "earnings_skipped_symbol_sessions",
                                       "all_checks_passed")}
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        if trades:
            with (out / "trades.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(trades[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(trades)
        else:
            (out / "trades.csv").write_text("no trades\n", encoding="utf-8")
        with (out / "skips.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["session", "symbol", "reason", "signal_time"], lineterminator="\n",
                               extrasaction="ignore")
            w.writeheader()
            w.writerows(skips)
        equity.rename("equity").rename_axis("session").to_csv(out / "daily_equity.csv", lineterminator="\n")
        (out / "metrics.json").write_text(json.dumps(metrics, indent=1, default=str), encoding="utf-8")
        (out / "report.md").write_text(render_report(metrics), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    return 0 if metrics["all_checks_passed"] else 1


def fmt(v, pct=False):
    if v == NA or v is None:
        return NA
    return f"{v * 100:.2f}%" if pct else (f"{v:.4f}" if isinstance(v, float) else str(v))


def render_report(m: dict) -> str:
    bh = m["benchmarks"]["equal_weight_buy_and_hold"]
    lines = [
        "# ORB smoke test (local cache only)", "",
        f"- Range: {m['range']['start']} → {m['range']['end']} ({m['range']['sessions']} sessions)",
        f"- Universe: {m['universe']['count']} tickers; with trades: {', '.join(m['universe']['symbols_with_trades']) or 'none'}",
        f"- Data: `{m['inputs']['cache_dir']}` (network {m['inputs']['network']}); earnings: `{m['inputs']['earnings_calendar']}`",
        "- Smoke test on 60 sessions of IEX 5m data: **not evidence of an edge**.", "",
        "| Metric | ORB | Equal-weight B&H |", "|---|---|---|",
        f"| Trades | {m['trades']} | — |",
        f"| Win rate | {fmt(m['win_rate'], True)} | — |",
        f"| Net return | {fmt(m['net_return'], True)} | {fmt(bh.get('net_return', NA), True)} |",
        f"| CAGR ({m.get('cagr_note', '')}) | {fmt(m['cagr'], True)} | {fmt(bh.get('cagr', NA), True)} |",
        f"| Max drawdown | {fmt(m['max_drawdown'], True)} | {fmt(bh.get('max_drawdown', NA), True)} |",
        f"| Sharpe (daily, √252) | {fmt(m['sharpe'])} | {fmt(bh.get('sharpe', NA))} |",
        f"| Sortino (daily, √252) | {fmt(m['sortino'])} | {fmt(bh.get('sortino', NA))} |", "",
        f"- Exits: {m['exits']}",
        f"- Costs: commission ${m['costs']['commission_total']:.2f}, slippage ${m['costs']['slippage_total']:.2f} ({m['costs']['note']})",
        f"- Skips: {m['skips']}; earnings-skipped symbol-sessions: {m['earnings_skipped_symbol_sessions']}",
        f"- Capital-constrained B&H: {m['benchmarks']['capital_constrained_buy_and_hold']['reason']}", "",
        "## Checks", "", "| Check | Status | Detail |", "|---|---|---|",
        *[f"| {c['check']} | {c['status']} | {c['detail']} |" for c in m["checks"]], "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
