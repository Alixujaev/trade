# Telegram control bot — design

**Date:** 2026-08-16
**Status:** Approved for implementation planning
**Relationship to `SPEC.md`:** This is an addition on top of the v1.0 Phase 1 system
in `SPEC.md`, not a change to it. All Hard Invariants (`SPEC.md` §4) continue to
apply unchanged — this bot is still signal-only (INV-9), still gates every symbol
through the sharia whitelist (INV-5), still places no orders. Where this document is
silent, `SPEC.md` governs.

## Motivation

The user wants to trigger backtests and live signal checks, and check current
positions, from their phone via Telegram — instead of opening a terminal on the
laptop. This requires an always-on process that listens for Telegram messages, which
is a deliberate, explicit deviation from `SPEC.md` §12/G6 ("no always-on process
required"). The user was told this trade-off explicitly and confirmed they want it.

## Non-goals (for this feature)

- No inline-button UI — Telegram's native "/" command menu only (user's choice).
- No per-command parameters (e.g. `/backtest AAPL` for a single symbol) — every
  command operates on the whole whitelist, matching the existing CLI entry points.
- No internal scheduler / auto-run-on-a-timer inside the bot — command-triggered
  only. (The existing cron/Task Scheduler + `live_main.py` path from `SPEC.md` §12
  still exists independently if the user wants it later; this feature doesn't
  replace it, just adds a manual/on-demand trigger.)
- No webhook support — long-polling only (works identically on laptop and future
  VPS, needs no public endpoint).
- No multi-user support — the bot answers only the single `chat_id` in `.env`.

## Architecture

One new root-level entry point, `telegram_bot.py`, sitting alongside
`backtest_main.py` and `live_main.py`. To avoid duplicating pipeline logic across
three entry points, `backtest_main.py` and `live_main.py` are refactored to expose
their core work as importable functions (behavior unchanged for existing CLI users):

- `backtest_main.py` gains `run_all_backtests(cfg) -> list[tuple[str, dict]]`
  (the existing per-symbol backtest loop, extracted from `main()`) and
  `format_metrics_table(rows) -> str` (existing `_print_metrics_table` split into a
  pure formatter + a thin `print()` wrapper). `main()` becomes
  `print(format_metrics_table(run_all_backtests(cfg)))`.
- `live_main.py` gains `build_live_engine(cfg) -> LiveEngine` (constructs the
  `YFinanceSource`/`TelegramAlertSink`/`LiveEngine` triple currently inlined in
  `main()`) and `format_signals(signals) -> str`. `main()` becomes
  `build_live_engine(cfg).run_once(symbols)` + `print(format_signals(...))`.

`telegram_bot.py` imports these functions plus `build_strategy` and `WHITELIST_PATH`
from `backtest_main`, exactly as `live_main.py` already does — same parity guarantee
(INV-2), no new strategy code path.

## Components

### Polling loop

```
run_forever(cfg: AppConfig) -> None:
    _register_commands(cfg)          # setMyCommands, once, best-effort
    offset = 0
    while True:
        try:
            updates = fetch_updates(cfg, offset, timeout=30)
        except requests.exceptions.RequestException:
            log warning; sleep(5); continue
        for update in updates:
            offset = update["update_id"] + 1
            dispatch(update, cfg)
```

- `fetch_updates(cfg, offset, timeout)` — thin wrapper over Telegram's `getUpdates`
  (long-polling: the request blocks server-side up to `timeout` seconds waiting for
  a new message, so the loop isn't hammering the API).
- `dispatch(update, cfg)` — authorizes, routes, replies. Never raises: all
  exceptions from a command handler are caught inside `dispatch` itself (see Error
  handling).

### Update filtering

Telegram's `getUpdates` can return update types other than a plain text message
(`edited_message`, `channel_post`, `callback_query`, ...). `dispatch` first checks
for `update.get("message", {}).get("text")`; if either is missing, the update is
silently skipped (not an error — just not a command).

### Authorization

`_is_authorized(update, cfg) -> bool` compares the update's `message.chat.id`
(stringified) against `cfg.telegram_chat_id`. Unauthorized updates are dropped
silently — no reply sent, nothing logged at a level that would leak information
back to the sender (a debug-level log locally is fine).

### Commands

Each command handler takes `cfg` and returns the reply text (a pure-ish function
modulo network calls) — this is what makes them independently testable:

| Command | Handler | Behavior |
|---|---|---|
| `/run` | `handle_run(cfg) -> str` | `build_live_engine(cfg).run_once(symbols)` (this already sends any changed-signal alerts via the existing `TelegramAlertSink`, unchanged). Returns a one-line summary: either `"Tekshirildi: N ta signal (...)"` listing symbol+action, or `"Tekshirildi, o'zgarish yo'q."` if `signals` is empty. |
| `/backtest` | `handle_backtest(cfg) -> str` | `format_metrics_table(run_all_backtests(cfg))`. |
| `/status` | `handle_status(cfg) -> str` | Reads `cfg.state_file` directly (no network), lists each whitelist symbol with its stored position (`flat`/`long`); symbols never yet seen in state show as `flat` (default 0, consistent with `LiveEngine`'s own default). |
| `/help` | `handle_help() -> str` | Static text listing the four commands. |
| anything else | — | `"Noma'lum buyruq. /help"` |

Command text matching is a simple prefix check on `update["message"]["text"]`
(`"/run"`, `"/backtest"`, `"/status"`, `"/help"`) — Telegram may suffix commands with
`@botusername` in group chats; strip that before matching. (This bot is single-user
so group usage isn't a target, but the strip is one line and avoids a footgun if the
user ever adds the bot to a group.)

### Command menu registration

`_register_commands(cfg)` calls Telegram's `setMyCommands` once at startup with the
four commands and short descriptions, so Telegram's native "/" picker shows them.
Best-effort: failure here is logged and does not prevent the bot from starting (the
commands still work if typed manually even if the menu registration call fails).

## Error handling

- **Transient network failure on `fetch_updates`:** caught (`requests.exceptions.RequestException`), logged at WARNING, loop sleeps briefly and retries — mirrors the existing swallow-and-log pattern in `alerts/telegram.py` (FR-31) and the per-symbol isolation pattern in `engine/live.py` (FR-28).
- **Exception inside a command handler:** caught inside `dispatch`, logged with
  full traceback, and a short `"Xatolik yuz berdi: ..."` reply is sent to the chat
  so the user gets feedback instead of silence. This is a new per-command isolation
  boundary, same rationale as FR-28's per-symbol boundary — `except Exception` is
  justified here for the same reason it's justified there.
- **`sendMessage` failure when replying:** reuses `TelegramAlertSink`'s existing
  swallow-and-log behavior where the reply is a `Signal`-driven alert (the `/run`
  path); for direct command replies (`/backtest`, `/status`, `/help`, error text)
  the same try/except-and-log pattern is applied inline in `dispatch`.

## Testing plan (offline, no network — same pattern as existing `tests/smoke_test.py`)

Following the project's existing convention (`test_telegram_alert_sink` monkeypatches
`requests.post`), new test functions will monkeypatch `requests.get` and
`requests.post` to avoid any real network access:

1. `format_metrics_table` / `format_signals` / `handle_status` output — pure
   formatting checks against known inputs.
2. Authorization: an update from a non-owner `chat_id` is dropped — no
   `sendMessage` call happens, handler not invoked.
3. Routing: `/status`, `/run`, `/backtest`, `/help`, and an unrecognized command
   each reach the correct handler / fallback reply.
4. Error isolation: a handler that raises still results in exactly one
   `sendMessage` call (the error reply), and `dispatch` itself does not raise.
5. Offset advancement: given a batch of fake updates from `fetch_updates`, the loop
   computes the correct next `offset` (`max(update_id) + 1`).
6. `backtest_main.py` / `live_main.py` refactor regression: existing
   `test_entry_points_import_and_share_strategy` continues to pass unchanged, plus a
   new assertion that `run_all_backtests`/`format_metrics_table` and
   `build_live_engine`/`format_signals` exist and are used by `main()` (import-level
   check, not a behavior change).
7. Update filtering: an update with no `message.text` (e.g. `edited_message`,
   `callback_query`) is skipped without error and without a reply.

`telegram_bot.py`'s outermost `run_forever` loop (infinite by construction) is not
itself unit-tested — `dispatch`, `fetch_updates`, and the handlers are, and that
covers all the branching logic. This mirrors how `engine/live.py` tests
`process_symbol`/`run_once` directly rather than any hypothetical outer scheduler.

## Open assumptions (flagging, not blocking)

- Long-polling `timeout=30` and retry-sleep `5s` on failure are reasonable defaults,
  not user-specified; easy to tune later.
- The bot process itself needs to be started manually (`py telegram_bot.py` in a
  terminal left open) for v1 — no Windows service/autostart wiring is in scope here
  unless requested separately.
