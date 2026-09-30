import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from backtest.day_engine import run_day_backtest, run_day_backtest_reference, format_day_backtest_report
from backtest.day_types import ExecutionConfig

def main():
    print("=" * 60)
    print("DAY-03 DAY BACKTEST PERFORMANCE BENCHMARK")
    print("=" * 60)

    df_5m = pd.read_parquet("data/cache/AAPL_5m.parquet")
    df_15m = pd.read_parquet("data/cache/AAPL_15m.parquet")

    config = ExecutionConfig()

    # Part 1: Shared deterministic sample benchmark & equivalence verification
    sample_size = 500
    df_5m_sample = df_5m.iloc[:sample_size]
    sample_end_time = df_5m_sample.index[-1] + pd.Timedelta(minutes=5)
    df_15m_sample = df_15m.loc[df_15m.index + pd.Timedelta(minutes=15) <= sample_end_time]

    print(f"\n1. Measuring reference vs optimized on shared sample ({sample_size} bars):")

    t0 = time.perf_counter()
    res_ref = run_day_backtest_reference("AAPL", df_5m=df_5m_sample, df_15m=df_15m_sample, config=config)
    t_ref_sample = time.perf_counter() - t0

    t0 = time.perf_counter()
    res_opt_sample = run_day_backtest("AAPL", df_5m=df_5m_sample, df_15m=df_15m_sample, config=config, use_fast_engine=True)
    t_opt_sample = time.perf_counter() - t0

    # Verify equivalence
    assert len(res_ref.trades) == len(res_opt_sample.trades), "Trade count mismatch!"
    for t1, t2 in zip(res_ref.trades, res_opt_sample.trades):
        assert t1.entry_time == t2.entry_time
        assert abs(t1.entry_price - t2.entry_price) < 1e-6
        assert t1.exit_time == t2.exit_time
        assert abs(t1.exit_price - t2.exit_price) < 1e-6
        assert t1.exit_reason == t2.exit_reason
        assert abs(t1.r_multiple - t2.r_multiple) < 1e-6

    speedup_sample = t_ref_sample / t_opt_sample if t_opt_sample > 0 else float("inf")
    print(f"  Reference engine ({sample_size} bars): {t_ref_sample:.3f} s")
    print(f"  Optimized engine ({sample_size} bars): {t_opt_sample:.3f} s")
    print(f"  Sample speedup factor: {speedup_sample:.1f}x")
    print(f"  Verification: 100% IDENTICAL ({len(res_ref.trades)} trades verified)")

    # Part 2: Full dataset replay with optimized engine
    print(f"\n2. Replaying FULL historical dataset ({len(df_5m)} bars, {df_5m.index[0].strftime('%Y-%m-%d')} to {df_5m.index[-1].strftime('%Y-%m-%d')}):")
    t0 = time.perf_counter()
    res_full = run_day_backtest("AAPL", df_5m=df_5m, df_15m=df_15m, config=config, use_fast_engine=True)
    t_opt_full = time.perf_counter() - t0

    # Reference engine O(N^2) complexity estimation:
    # Scaling factor = (4680 / 500)^2 = 87.6x -> 87.6 * t_ref_sample
    estimated_ref_full = t_ref_sample * ((len(df_5m) / sample_size) ** 2)
    overall_speedup = estimated_ref_full / t_opt_full

    print(f"  Optimized engine runtime: {t_opt_full:.3f} s")
    print(f"  Estimated reference runtime (O(N^2) scaling): {estimated_ref_full:.1f} s (~{estimated_ref_full/60:.1f} min)")
    print(f"  Estimated speedup factor: ~{overall_speedup:.0f}x")

    print("\n" + "=" * 60)
    print("AAPL FULL BACKTEST REPORT")
    print("=" * 60)
    report = format_day_backtest_report(res_full)
    print(report)

if __name__ == "__main__":
    main()
