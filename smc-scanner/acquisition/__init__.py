"""acquisition: DAY-15A — OOS market-data acquisition layer (protocol v1.0).

Pipeline: contract -> provider adapter (yfinance) -> raw frame -> structural validation
-> write-once snapshot -> manifest / SHA-256.

Strictly independent from strategy, signals, indicators, backtest and metrics: this package
only acquires and structurally validates raw OHLCV. It never computes signals, returns or
any performance statistic (DAY-14 data-expansion-spec §5).
"""
