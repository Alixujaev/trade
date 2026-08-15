# Telegram Control Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user trigger `/run` (live signal check), `/backtest`, and `/status`
from Telegram itself, via a new always-on `telegram_bot.py` process that long-polls
Telegram's `getUpdates` API and replies through the existing Bot API.

**Architecture:** Extract the per-symbol work already inside `backtest_main.py` and
`live_main.py`'s `main()` functions into reusable functions
(`run_all_backtests`/`format_metrics_table` and
`build_live_engine`/`format_signals`), so `telegram_bot.py` can call the exact same
code the CLI entry points use (no duplicated logic, same backtest/live parity
guarantee the rest of the system already relies on). `telegram_bot.py` itself is a
thin polling loop + command router on top of those functions.

**Tech Stack:** Python 3.10+, `requests` for the Telegram Bot API (no new
dependencies), existing `core.config.AppConfig`.

**Spec:** `docs/superpowers/specs/2026-08-16-telegram-control-bot-design.md`

## Global Constraints

- Every module starts with `from __future__ import annotations` (existing project
  convention, all current files follow it).
- No bare `except:`. `except Exception` is reserved for isolation boundaries only
  (per-symbol in `engine/live.py`, per-command in `telegram_bot.py`'s `dispatch`) —
  same rationale as `SPEC.md` FR-28.
- No new dependencies. Telegram API calls go through `requests` directly, exactly
  like `alerts/telegram.py` — no bot framework/SDK.
- Bot replies only to the `chat_id` configured in `.env` (`TELEGRAM_CHAT_ID`, loaded
  via `AppConfig.telegram_chat_id`). Any other sender is silently ignored.
- Tests are offline only, appended to `tests/smoke_test.py` following its existing
  pattern: monkeypatch `requests.get`/`requests.post` (see
  `test_telegram_alert_sink` in that file for the established style), print
  `"[ok] <name>"` at the end of each test function, and append the function to the
  `tests` list in `main()`. No new test file, no `pytest` dependency introduced
  (project already has it installed for convenience, but `tests/smoke_test.py` stays
  plain-`assert`-based and runnable via `python -m tests.smoke_test`).
- Definition of done for every task: `py -m tests.smoke_test` exits 0 and prints
  `[ok]` for every test including the new one(s), and
  `py -m py_compile <every changed/new .py file>` succeeds.
- Run all commands from the repo root: `C:\Users\user\Desktop\Own\trade-bot`. Use
  the `py` launcher (confirmed working in this environment; plain `python` is not on
  PATH).

---

## Task 1: Extract `run_all_backtests` / `format_metrics_table` from `backtest_main.py`

**Files:**
- Modify: `backtest_main.py` (currently 73 lines)
- Test: `tests/smoke_test.py`

**Interfaces:**
- Produces: `backtest_main.run_all_backtests(cfg: AppConfig) -> list[tuple[str, dict]]`
  — loads the whitelist, builds the strategy, runs a backtest per symbol, returns
  `(symbol, metrics_dict)` pairs. Same behavior as today's `main()` body, just
  callable independently.
- Produces: `backtest_main.format_metrics_table(rows: list[tuple[str, dict]]) -> str`
  — pure formatter, returns the table as a string instead of printing it directly.

- [ ] **Step 1: Write the failing test**

Open `tests/smoke_test.py` and add this function right before `def main() -> int:`:

```python
def test_backtest_main_helpers() -> None:
    import backtest_main

    rows = [
        (
            "AAPL",
            {
                "total_return_pct": 12.3,
                "cagr_pct": 6.7,
                "sharpe": 1.2,
                "max_drawdown_pct": -5.5,
                "num_trades": 3,
                "win_rate_pct": 66.7,
                "avg_win": 10.0,
                "avg_loss": -4.0,
                "expectancy_per_trade": 42.0,
            },
        ),
    ]
    table = backtest_main.format_metrics_table(rows)
    assert table.startswith("symbol\ttotal_return_pct\t")
    assert "AAPL\t12.30\t6.70\t1.20\t-5.50\t3\t66.70\t42.00" in table

    assert backtest_main.format_metrics_table([]) == "No results."

    assert callable(backtest_main.run_all_backtests)

    print("[ok] backtest_main_helpers")
```

Also add `test_backtest_main_helpers` to the `tests` list inside `main()`, right
after `test_entry_points_import_and_share_strategy,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m tests.smoke_test`
Expected: FAIL with `AttributeError: module 'backtest_main' has no attribute
'format_metrics_table'` (raised from inside `test_backtest_main_helpers`, after the
earlier tests print their `[ok]` lines).

- [ ] **Step 3: Refactor `backtest_main.py`**

Replace the `_print_metrics_table` function and the `main` function (everything from
`def _print_metrics_table` down to the `if __name__ == "__main__":` block at the end
of the file) with:

```python
def run_all_backtests(cfg: AppConfig) -> list[tuple[str, dict]]:
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    strategy = build_strategy(cfg)
    source = YFinanceSource()

    rows: list[tuple[str, dict]] = []
    for symbol in symbols:
        try:
            df = source.get_history(symbol, cfg.lookback_days, cfg.interval)
            result = run_backtest(df, strategy, cfg.backtest, symbol)
            rows.append((symbol, compute_metrics(result)))
        except Exception:
            logger.exception("backtest failed for %s", symbol)

    return rows


def format_metrics_table(rows: list[tuple[str, dict]]) -> str:
    if not rows:
        return "No results."

    lines = ["symbol\t" + "\t".join(_METRIC_COLUMNS)]
    for symbol, metrics in rows:
        values = [symbol]
        for col in _METRIC_COLUMNS:
            v = metrics[col]
            values.append(str(v) if col == "num_trades" else f"{v:.2f}")
        lines.append("\t".join(values))
    return "\n".join(lines)


def main() -> None:
    cfg = AppConfig.from_env()
    print(format_metrics_table(run_all_backtests(cfg)))


if __name__ == "__main__":
    main()
```

The rest of the file (imports, `logging.basicConfig`, `WHITELIST_PATH`,
`_METRIC_COLUMNS`, `build_strategy`) is unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m tests.smoke_test`
Expected: every line ends with `[ok] ...`, including `[ok] backtest_main_helpers`,
and the process exits 0.

Also run: `py -m py_compile backtest_main.py tests/smoke_test.py`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add backtest_main.py tests/smoke_test.py
git commit -m "refactor: extract run_all_backtests/format_metrics_table from backtest_main"
```

---

## Task 2: Extract `build_live_engine` / `format_signals` from `live_main.py`

**Files:**
- Modify: `live_main.py` (currently 34 lines)
- Test: `tests/smoke_test.py`

**Interfaces:**
- Consumes: `backtest_main.WHITELIST_PATH`, `backtest_main.build_strategy` (already
  imported by `live_main.py` today — unchanged).
- Produces: `live_main.build_live_engine(cfg: AppConfig) -> LiveEngine` — builds the
  `YFinanceSource`/`TelegramAlertSink`/`LiveEngine` triple currently inlined in
  `main()`.
- Produces: `live_main.format_signals(signals: list[Signal]) -> str` — pure
  formatter: `"Tekshirildi, o'zgarish yo'q."` if `signals` is empty, otherwise
  `"Tekshirildi: N ta signal (SYM ACTION, SYM ACTION)."`.

- [ ] **Step 1: Write the failing test**

Add to `tests/smoke_test.py`, right before `def main() -> int:` (after
`test_backtest_main_helpers`):

```python
def test_live_main_helpers() -> None:
    import live_main
    from core.models import Action, Signal

    assert live_main.format_signals([]) == "Tekshirildi, o'zgarish yo'q."

    sigs = [
        Signal(
            symbol="MSFT",
            timestamp="2024-01-02",
            target_position=1,
            action=Action.BUY,
            reason="x",
            price=1.0,
        ),
        Signal(
            symbol="NVDA",
            timestamp="2024-01-02",
            target_position=0,
            action=Action.SELL,
            reason="y",
            price=2.0,
        ),
    ]
    text = live_main.format_signals(sigs)
    assert text == "Tekshirildi: 2 ta signal (MSFT BUY, NVDA SELL)."

    assert callable(live_main.build_live_engine)

    print("[ok] live_main_helpers")
```

Add `test_live_main_helpers` to the `tests` list in `main()`, right after
`test_backtest_main_helpers,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m tests.smoke_test`
Expected: FAIL with `AttributeError: module 'live_main' has no attribute
'format_signals'`.

- [ ] **Step 3: Refactor `live_main.py`**

Replace the whole file with:

```python
from __future__ import annotations

import logging

from alerts.telegram import TelegramAlertSink
from backtest_main import WHITELIST_PATH, build_strategy
from core.config import AppConfig
from core.models import Signal
from data.yfinance_source import YFinanceSource
from engine.live import LiveEngine
from screening.sharia import ShariaFilter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_live_engine(cfg: AppConfig) -> LiveEngine:
    source = YFinanceSource()
    alert = TelegramAlertSink(cfg.telegram_bot_token, cfg.telegram_chat_id)
    return LiveEngine(source, build_strategy(cfg), alert, cfg)


def format_signals(signals: list[Signal]) -> str:
    if not signals:
        return "Tekshirildi, o'zgarish yo'q."
    parts = ", ".join(f"{s.symbol} {s.action.value}" for s in signals)
    return f"Tekshirildi: {len(signals)} ta signal ({parts})."


def main() -> None:
    cfg = AppConfig.from_env()
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    symbols = whitelist.filter(sorted(whitelist.whitelist))

    engine = build_live_engine(cfg)
    signals = engine.run_once(symbols)
    print(format_signals(signals))


if __name__ == "__main__":
    main()
```

Note: this changes `main()`'s output from per-signal `logger.info` lines to a single
`print(format_signals(...))` summary line — an intentional, already-approved change
(see the design doc's Architecture section) so the CLI and the future `/run` Telegram
command share one formatter.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m tests.smoke_test`
Expected: all `[ok]` lines including `[ok] live_main_helpers`, exit 0.

Also run: `py -m py_compile live_main.py tests/smoke_test.py`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add live_main.py tests/smoke_test.py
git commit -m "refactor: extract build_live_engine/format_signals from live_main"
```

---

## Task 3: `telegram_bot.py` — command parsing, authorization, `/help`

**Files:**
- Create: `telegram_bot.py`
- Test: `tests/smoke_test.py`

**Interfaces:**
- Consumes: `core.config.AppConfig` (existing).
- Produces: `telegram_bot.COMMANDS: list[tuple[str, str]]` (command name without
  slash, description pairs — used later by `register_commands` and `handle_help`).
- Produces: `telegram_bot._is_authorized(update: dict, cfg: AppConfig) -> bool`.
- Produces: `telegram_bot._command_text(update: dict) -> str | None`.
- Produces: `telegram_bot.handle_help() -> str`.

This task creates the file with only these pieces — no network calls yet, so the
test is fully offline with no monkeypatching needed. Later tasks append more to the
same file.

- [ ] **Step 1: Write the failing test**

Add to `tests/smoke_test.py`, right before `def main() -> int:` (after
`test_live_main_helpers`):

```python
def test_telegram_bot_auth_and_parsing() -> None:
    import telegram_bot
    from core.config import AppConfig

    cfg = AppConfig(telegram_bot_token="TOK", telegram_chat_id="881912596")

    owner_update = {"message": {"chat": {"id": 881912596}, "text": "/status"}}
    stranger_update = {"message": {"chat": {"id": 111}, "text": "/status"}}
    assert telegram_bot._is_authorized(owner_update, cfg)
    assert not telegram_bot._is_authorized(stranger_update, cfg)
    # chat id as string still matches (Telegram sends ints; cfg stores str from env)
    assert telegram_bot._is_authorized(
        {"message": {"chat": {"id": "881912596"}, "text": "hi"}}, cfg
    )
    assert not telegram_bot._is_authorized({"edited_message": {}}, cfg)

    assert telegram_bot._command_text({"message": {"text": "/run"}}) == "/run"
    assert telegram_bot._command_text({"message": {"text": "/run@MyBot"}}) == "/run"
    assert (
        telegram_bot._command_text({"message": {"text": "/backtest now please"}})
        == "/backtest"
    )
    assert telegram_bot._command_text({"message": {}}) is None
    assert telegram_bot._command_text({"edited_message": {"text": "/run"}}) is None

    help_text = telegram_bot.handle_help()
    assert "/run" in help_text
    assert "/backtest" in help_text
    assert "/status" in help_text
    assert "/help" in help_text

    print("[ok] telegram_bot_auth_and_parsing")
```

Add `test_telegram_bot_auth_and_parsing` to the `tests` list in `main()`, right
after `test_live_main_helpers,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m tests.smoke_test`
Expected: FAIL with `ModuleNotFoundError: No module named 'telegram_bot'`.

- [ ] **Step 3: Create `telegram_bot.py`**

```python
from __future__ import annotations

from core.config import AppConfig

COMMANDS = [
    ("run", "Bugungi signalni tekshirish"),
    ("backtest", "Whitelist bo'yicha backtest ishga tushirish"),
    ("status", "Joriy pozitsiyalarni ko'rish"),
    ("help", "Yordam"),
]


def _is_authorized(update: dict, cfg: AppConfig) -> bool:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    return chat_id is not None and str(chat_id) == str(cfg.telegram_chat_id)


def _command_text(update: dict) -> str | None:
    message = update.get("message") or {}
    text = message.get("text")
    if not text:
        return None
    return text.split()[0].split("@")[0]


def handle_help() -> str:
    return "\n".join(f"/{c} — {d}" for c, d in COMMANDS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m tests.smoke_test`
Expected: all `[ok]` lines including `[ok] telegram_bot_auth_and_parsing`, exit 0.

Also run: `py -m py_compile telegram_bot.py tests/smoke_test.py`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot.py tests/smoke_test.py
git commit -m "feat: telegram_bot command parsing, auth, and /help"
```

---

## Task 4: `telegram_bot.py` — Telegram API wrappers

**Files:**
- Modify: `telegram_bot.py`
- Test: `tests/smoke_test.py`

**Interfaces:**
- Consumes: `telegram_bot.COMMANDS` (from Task 3).
- Produces: `telegram_bot.register_commands(cfg: AppConfig) -> None`.
- Produces: `telegram_bot.fetch_updates(cfg: AppConfig, offset: int, timeout: int = 30) -> list[dict]`.
- Produces: `telegram_bot.next_offset(updates: list[dict], current_offset: int) -> int`.
- Produces: `telegram_bot.send_reply(cfg: AppConfig, chat_id: int | str, text: str) -> None`.

All network calls go through `requests`; failures are caught and logged, never
raised (same pattern as `alerts/telegram.py`'s `send`).

- [ ] **Step 1: Write the failing test**

Add to `tests/smoke_test.py`, right before `def main() -> int:` (after
`test_telegram_bot_auth_and_parsing`):

```python
def test_telegram_bot_api_wrappers() -> None:
    import requests

    import telegram_bot
    from core.config import AppConfig

    cfg = AppConfig(telegram_bot_token="TOK", telegram_chat_id="123")

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    # fetch_updates: parses the "result" list, passes offset/timeout through
    get_calls = []

    def fake_get(url, params=None, timeout=None):
        get_calls.append((url, params, timeout))
        return _FakeResp({"ok": True, "result": [{"update_id": 5}, {"update_id": 6}]})

    orig_get = requests.get
    requests.get = fake_get
    try:
        updates = telegram_bot.fetch_updates(cfg, offset=5, timeout=30)
    finally:
        requests.get = orig_get
    assert updates == [{"update_id": 5}, {"update_id": 6}]
    assert "TOK" in get_calls[0][0]
    assert get_calls[0][1] == {"offset": 5, "timeout": 30}

    # next_offset: advances past the highest update_id seen; unchanged when empty
    assert telegram_bot.next_offset([], 5) == 5
    assert telegram_bot.next_offset([{"update_id": 5}, {"update_id": 7}], 5) == 8

    # send_reply: posts to sendMessage; failures are swallowed, never raised
    post_calls = []

    def fake_post_ok(url, json=None, timeout=None):
        post_calls.append((url, json, timeout))
        return _FakeResp({"ok": True})

    orig_post = requests.post
    requests.post = fake_post_ok
    try:
        telegram_bot.send_reply(cfg, 123, "salom")
    finally:
        requests.post = orig_post
    assert post_calls[0][1] == {"chat_id": 123, "text": "salom"}

    def fake_post_fail(url, json=None, timeout=None):
        raise requests.exceptions.ConnectionError("boom")

    requests.post = fake_post_fail
    try:
        telegram_bot.send_reply(cfg, 123, "salom")  # must not raise
    finally:
        requests.post = orig_post

    # register_commands: posts setMyCommands with all four commands
    reg_calls = []

    def fake_post_register(url, json=None, timeout=None):
        reg_calls.append((url, json, timeout))
        return _FakeResp({"ok": True})

    requests.post = fake_post_register
    try:
        telegram_bot.register_commands(cfg)
    finally:
        requests.post = orig_post
    assert "setMyCommands" in reg_calls[0][0]
    assert {
        "command": "run",
        "description": "Bugungi signalni tekshirish",
    } in reg_calls[0][1]["commands"]

    # register_commands: failures swallowed too
    requests.post = fake_post_fail
    try:
        telegram_bot.register_commands(cfg)  # must not raise
    finally:
        requests.post = orig_post

    print("[ok] telegram_bot_api_wrappers")
```

Add `test_telegram_bot_api_wrappers` to the `tests` list in `main()`, right after
`test_telegram_bot_auth_and_parsing,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m tests.smoke_test`
Expected: FAIL with `AttributeError: module 'telegram_bot' has no attribute
'fetch_updates'`.

- [ ] **Step 3: Append to `telegram_bot.py`**

Change the top of the file from:

```python
from __future__ import annotations

from core.config import AppConfig
```

to:

```python
from __future__ import annotations

import logging

import requests

from core.config import AppConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/{method}"
```

Then append at the end of the file (after `handle_help`):

```python
def _api_url(cfg: AppConfig, method: str) -> str:
    return API_URL.format(token=cfg.telegram_bot_token, method=method)


def register_commands(cfg: AppConfig) -> None:
    try:
        response = requests.post(
            _api_url(cfg, "setMyCommands"),
            json={"commands": [{"command": c, "description": d} for c, d in COMMANDS]},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logger.warning("failed to register telegram command menu", exc_info=True)


def fetch_updates(cfg: AppConfig, offset: int, timeout: int = 30) -> list[dict]:
    response = requests.get(
        _api_url(cfg, "getUpdates"),
        params={"offset": offset, "timeout": timeout},
        timeout=timeout + 10,
    )
    response.raise_for_status()
    return response.json().get("result", [])


def next_offset(updates: list[dict], current_offset: int) -> int:
    if not updates:
        return current_offset
    return max(u["update_id"] for u in updates) + 1


def send_reply(cfg: AppConfig, chat_id: int | str, text: str) -> None:
    try:
        response = requests.post(
            _api_url(cfg, "sendMessage"),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        logger.warning("failed to send telegram reply", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m tests.smoke_test`
Expected: all `[ok]` lines including `[ok] telegram_bot_api_wrappers`, exit 0.

Also run: `py -m py_compile telegram_bot.py tests/smoke_test.py`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot.py tests/smoke_test.py
git commit -m "feat: telegram_bot API wrappers (getUpdates/sendMessage/setMyCommands)"
```

---

## Task 5: `telegram_bot.py` — command handlers, dispatch, run_forever

**Files:**
- Modify: `telegram_bot.py`
- Test: `tests/smoke_test.py`

**Interfaces:**
- Consumes: `backtest_main.WHITELIST_PATH`, `backtest_main.format_metrics_table`,
  `backtest_main.run_all_backtests` (Task 1); `live_main.build_live_engine`,
  `live_main.format_signals` (Task 2); `screening.sharia.ShariaFilter` (existing).
- Consumes: `telegram_bot._is_authorized`, `_command_text`, `handle_help`,
  `send_reply`, `fetch_updates`, `next_offset`, `register_commands` (Tasks 3-4).
- Produces: `telegram_bot._load_symbols() -> list[str]`.
- Produces: `telegram_bot.handle_run(cfg: AppConfig) -> str`,
  `handle_backtest(cfg: AppConfig) -> str`, `handle_status(cfg: AppConfig) -> str`.
- Produces: `telegram_bot.dispatch(update: dict, cfg: AppConfig) -> None`.
- Produces: `telegram_bot.run_forever(cfg: AppConfig) -> None` (not unit-tested —
  see design doc's Testing plan section; everything it calls is tested here).

This is the integration point: everything built in Tasks 1-4 gets wired together.

- [ ] **Step 1: Write the failing test**

Add to `tests/smoke_test.py`, right before `def main() -> int:` (after
`test_telegram_bot_api_wrappers`):

```python
def test_telegram_bot_dispatch_and_handlers() -> None:
    import requests

    import telegram_bot
    from core.config import AppConfig
    from core.models import Action, Signal

    cfg = AppConfig(telegram_bot_token="TOK", telegram_chat_id="123")

    class _FakeEngine:
        def __init__(self):
            self.state = {"AAPL": 1, "MSFT": 0}

        def run_once(self, symbols):
            return [
                Signal(
                    symbol="AAPL",
                    timestamp="t",
                    target_position=1,
                    action=Action.BUY,
                    reason="x",
                    price=1.0,
                )
            ]

    def fake_backtest_rows(cfg):
        return [
            (
                "AAPL",
                {
                    "total_return_pct": 1.0,
                    "cagr_pct": 1.0,
                    "sharpe": 1.0,
                    "max_drawdown_pct": -1.0,
                    "num_trades": 1,
                    "win_rate_pct": 100.0,
                    "avg_win": 1.0,
                    "avg_loss": 0.0,
                    "expectancy_per_trade": 1.0,
                },
            )
        ]

    orig_build_engine = telegram_bot.build_live_engine
    orig_run_backtests = telegram_bot.run_all_backtests
    orig_load_symbols = telegram_bot._load_symbols
    telegram_bot.build_live_engine = lambda cfg: _FakeEngine()
    telegram_bot._load_symbols = lambda: ["AAPL", "MSFT"]
    telegram_bot.run_all_backtests = fake_backtest_rows
    try:
        assert telegram_bot.handle_run(cfg) == "Tekshirildi: 1 ta signal (AAPL BUY)."

        status = telegram_bot.handle_status(cfg)
        assert "AAPL: long" in status
        assert "MSFT: flat" in status

        backtest_text = telegram_bot.handle_backtest(cfg)
        assert "AAPL" in backtest_text

        # ---- dispatch: authorization, routing, error isolation ----
        sent = []

        def fake_post(url, json=None, timeout=None):
            sent.append(json)

            class _R:
                def raise_for_status(self):
                    pass

            return _R()

        orig_post = requests.post
        requests.post = fake_post
        try:
            # unauthorized sender: dropped silently, no reply
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 999}, "text": "/status"}}, cfg
            )
            assert sent == []

            # authorized /status
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/status"}}, cfg
            )
            assert len(sent) == 1
            assert "AAPL: long" in sent[0]["text"]

            # authorized /run
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/run"}}, cfg
            )
            assert len(sent) == 2
            assert sent[1]["text"] == "Tekshirildi: 1 ta signal (AAPL BUY)."

            # authorized /backtest (still the working fake at this point)
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/backtest"}}, cfg
            )
            assert len(sent) == 3
            assert "AAPL" in sent[2]["text"]

            # unknown command
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/bogus"}}, cfg
            )
            assert sent[3]["text"] == "Noma'lum buyruq. /help"

            # /help
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/help"}}, cfg
            )
            assert "/run" in sent[4]["text"]

            # non-message update types are ignored (no reply)
            telegram_bot.dispatch(
                {"edited_message": {"chat": {"id": 123}, "text": "/status"}}, cfg
            )
            assert len(sent) == 5

            # handler error is caught, reported to the chat, dispatch doesn't raise
            def broken_backtests(cfg):
                raise RuntimeError("boom")

            telegram_bot.run_all_backtests = broken_backtests
            telegram_bot.dispatch(
                {"message": {"chat": {"id": 123}, "text": "/backtest"}}, cfg
            )
            assert "Xatolik yuz berdi" in sent[5]["text"]
        finally:
            requests.post = orig_post
    finally:
        telegram_bot.build_live_engine = orig_build_engine
        telegram_bot.run_all_backtests = orig_run_backtests
        telegram_bot._load_symbols = orig_load_symbols

    print("[ok] telegram_bot_dispatch_and_handlers")
```

Add `test_telegram_bot_dispatch_and_handlers` to the `tests` list in `main()`, right
after `test_telegram_bot_api_wrappers,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m tests.smoke_test`
Expected: FAIL with `AttributeError: module 'telegram_bot' has no attribute
'build_live_engine'`.

- [ ] **Step 3: Append to `telegram_bot.py`**

Change the top of the file from:

```python
from __future__ import annotations

import logging

import requests

from core.config import AppConfig
```

to:

```python
from __future__ import annotations

import logging
import time

import requests

from backtest_main import WHITELIST_PATH, format_metrics_table, run_all_backtests
from core.config import AppConfig
from live_main import build_live_engine, format_signals
from screening.sharia import ShariaFilter
```

Then append at the end of the file (after `send_reply`):

```python
def _load_symbols() -> list[str]:
    whitelist = ShariaFilter.from_file(WHITELIST_PATH)
    return whitelist.filter(sorted(whitelist.whitelist))


def handle_run(cfg: AppConfig) -> str:
    engine = build_live_engine(cfg)
    signals = engine.run_once(_load_symbols())
    return format_signals(signals)


def handle_backtest(cfg: AppConfig) -> str:
    return format_metrics_table(run_all_backtests(cfg))


def handle_status(cfg: AppConfig) -> str:
    symbols = _load_symbols()
    if not symbols:
        return "Whitelist bo'sh."
    engine = build_live_engine(cfg)
    lines = [
        f"{symbol}: {'long' if engine.state.get(symbol, 0) == 1 else 'flat'}"
        for symbol in symbols
    ]
    return "\n".join(lines)


_HANDLERS = {
    "/run": handle_run,
    "/backtest": handle_backtest,
    "/status": handle_status,
}


def dispatch(update: dict, cfg: AppConfig) -> None:
    if not _is_authorized(update, cfg):
        return

    command = _command_text(update)
    if command is None:
        return

    chat_id = update["message"]["chat"]["id"]

    if command == "/help":
        send_reply(cfg, chat_id, handle_help())
        return

    handler = _HANDLERS.get(command)
    if handler is None:
        send_reply(cfg, chat_id, "Noma'lum buyruq. /help")
        return

    try:
        reply = handler(cfg)
    except Exception as exc:
        logger.exception("command %s failed", command)
        send_reply(cfg, chat_id, f"Xatolik yuz berdi: {exc}")
        return

    send_reply(cfg, chat_id, reply)


def run_forever(cfg: AppConfig) -> None:
    register_commands(cfg)
    offset = 0
    while True:
        try:
            updates = fetch_updates(cfg, offset)
        except requests.exceptions.RequestException:
            logger.warning("failed to fetch telegram updates; retrying", exc_info=True)
            time.sleep(5)
            continue

        for update in updates:
            dispatch(update, cfg)
        offset = next_offset(updates, offset)


if __name__ == "__main__":
    run_forever(AppConfig.from_env())
```

Note the `_HANDLERS` dict binds the function objects at module-load time; the test
in Step 1 monkeypatches `telegram_bot.build_live_engine` /
`telegram_bot.run_all_backtests` / `telegram_bot._load_symbols` directly (not
`_HANDLERS`), which works because `handle_run`/`handle_backtest`/`handle_status`
look up those names from the module's global namespace at *call* time, not at
definition time.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m tests.smoke_test`
Expected: all `[ok]` lines including `[ok] telegram_bot_dispatch_and_handlers`,
exit 0.

Also run: `py -m py_compile telegram_bot.py tests/smoke_test.py`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add telegram_bot.py tests/smoke_test.py
git commit -m "feat: telegram_bot command handlers, dispatch, and run_forever"
```

---

## Task 6: README + final regression + push

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation + verification only).

- [ ] **Step 1: Add a "Telegram control bot" section to `README.md`**

Insert this new section right after the existing "## Run" section (before
"## Architecture"):

```markdown
## Telegram control bot (optional)

Instead of running `backtest_main.py`/`live_main.py` from a terminal, you can run a
long-lived process that listens for Telegram commands and replies in the chat:

```bash
python telegram_bot.py
```

This is an always-on process — a deliberate exception to this project's usual "no
always-on process" design (see `SPEC.md` §12) — leave the terminal open, or run it
under a process manager, while you want to use it. It only responds to the
`TELEGRAM_CHAT_ID` configured in `.env`; every other sender is silently ignored.

Commands (also shown via Telegram's native "/" menu once the bot has started once):

- `/run` — run one live signal check now, same as `python live_main.py`.
- `/backtest` — run a backtest over the whitelist, same as `python backtest_main.py`.
- `/status` — show each whitelist symbol's current stored position, instantly, with
  no network call.
- `/help` — list the commands.

Design rationale and testing approach:
`docs/superpowers/specs/2026-08-16-telegram-control-bot-design.md`.
```

- [ ] **Step 2: Run the full test suite one more time**

Run: `py -m tests.smoke_test`
Expected: every test's `[ok]` line prints (12 from Phase 1 plus the 5 added in
Tasks 1-5), process exits 0.

- [ ] **Step 3: Byte-compile every module**

Run:

```bash
py -m py_compile core/models.py core/config.py data/base.py data/yfinance_source.py indicators/indicators.py signals/base.py signals/strategies.py screening/sharia.py alerts/base.py alerts/telegram.py broker/base.py engine/backtest.py engine/live.py tests/smoke_test.py backtest_main.py live_main.py telegram_bot.py
```

Expected: no output, exit 0.

- [ ] **Step 4: Manual smoke check (requires the real `.env` and `whitelist.txt` already in place)**

Run `py telegram_bot.py` in a terminal, leave it running, and from Telegram send
`/status` then `/help` to the bot to confirm real replies arrive. Stop it with
Ctrl+C once confirmed. (This step is manual — there is no automated test for the
live network path, matching the rest of this project's testing boundary.)

- [ ] **Step 5: Commit and push**

```bash
git add README.md
git commit -m "docs: document the telegram control bot"
git push
```
