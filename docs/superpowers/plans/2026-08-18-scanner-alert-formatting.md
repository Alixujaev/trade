# Scanner Alert Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the price-action Scanner's generic Telegram alert text with a
purpose-built, scannable format (fixed header emoji, `Trigger:`/`Context:`/
`Price:`/`Bar:` lines, mandatory "not a trade signal" closer) so a user can decide
in ~3 seconds whether to look at a setup, without touching detection logic, the
strategy (`live_main.py`) alert path, or any invariant.

**Architecture:** A new pure function `format_setup_alert_text(setup, bar_date)` in
`signals/detectors.py` — co-located with `Setup` and the `_ROUND_NUMBER_UNIT`
constant it needs for "near $&lt;level&gt;" — is the single source of truth for
mapping internal trigger/context keys to human-readable labels and assembling the
exact alert body. `Signal` gains an optional `formatted_text` field that, when set,
`TelegramAlertSink.send()` sends verbatim instead of building its existing generic
template. `Scanner._to_signal` is the only caller that ever sets it, so
`live_main.py`/`engine/live.py` and their alerts are provably untouched — they
never construct a `Signal` with `formatted_text`, so `TelegramAlertSink` keeps
building the old template for them exactly as before. The scanner's `reason`
string (already asserted by an existing test) is left unchanged, so it keeps
serving as the internal/log summary while `formatted_text` becomes the actual
Telegram-visible payload.

**Tech Stack:** Python ≥ 3.10, existing project stack (`pandas`) — no new
dependencies. Emoji/box-drawing checks use only the stdlib `unicodedata` and `re`
modules.

**Spec:** `SPEC.md` (base project spec). This plan implements a presentation-only
change on top of the already-merged Scanner (`docs/superpowers/plans/2026-08-17-price-action-scanner.md`);
no functional/detection requirement changes.

## Global Constraints

- Every new/modified module already has `from __future__ import annotations` —
  do not remove it; no new file is created by this plan, so no new file needs one.
- No bare `except:` (unchanged in this plan — no new exception handling is added).
- No new dependencies (SPEC §5: `pandas`, `requests`, `python-dotenv` are the
  pinned stack; this plan doesn't need anything beyond stdlib + `pandas`, both
  already present in the touched files).
- **INV-2 (Parity):** not affected — no indicator/strategy math is touched.
- **INV-5 (Sharia gate):** not affected — this plan touches presentation only,
  after the whitelist gate has already run.
- **INV-9 (Signal-only):** not affected — no order-related code is added or
  touched.
- Tests are offline only, plain `assert`-based, one `test_xxx()` function per
  concern, each ending with `print("[ok] <name>")`, registered in a `tests` list
  inside each file's `main()`, runnable via `python -m tests.scanner_test` /
  `python -m tests.smoke_test`. No `pytest` dependency.
- Definition of done for every task: the relevant test module exits 0 with every
  `[ok]` line printed (old and new), the OTHER test module (smoke vs. scanner)
  still exits 0 untouched, and `python -m py_compile <every changed file>`
  succeeds.
- Run all commands from the repo root: `C:\Users\Admin\Desktop\own\trade`.
  `python` is confirmed on `PATH` (`python --version` → 3.12.10).
- Do not modify `engine/live.py`, `live_main.py`, or any existing assertion in
  `tests/smoke_test.py`/`tests/scanner_test.py` — only add to them.

## Design Decisions & Resolved Ambiguities

Ranked by severity — flag to the user if they'd prefer a different call; none of
them change the task's Do-NOT list.

1. **(Medium) The task prompt's own example is internally inconsistent.** It shows
   `Price: $228.50` alongside `Context: ... near $225`, but this plan's own
   round-number formula (`round(price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT`,
   reusing the existing `_ROUND_NUMBER_UNIT = 5.0` from `near_round_number`) gives
   `round(228.50 / 5) * 5 = 230`, not `225`. The example is illustrative, not a
   literal computed pair. This plan computes the level honestly from the real
   formula rather than hardcoding `225`; the tests below pick prices where the
   computed level is unambiguous and self-consistent (e.g. `226.30 → 225`).
2. **(Low) `reason` is left unchanged, not reformatted.** The task says "map
   internal keys to readable labels" for the alert; it does not ask for `reason`
   (an internal/log field, not Telegram-visible once `formatted_text` is set) to
   change, and an existing test
   (`test_scanner_alert_on_change_and_state`, `tests/scanner_test.py:367`)
   already asserts `reason`'s exact old framing string. Changing `reason` would
   either break that test or require rewriting it, and the task says "keep all
   existing tests green." Resolution: `reason` keeps its current content
   (unchanged code), `formatted_text` carries 100% of the new user-facing format.
3. **(Low) `Signal.formatted_text` placement.** Added as the new *last* field of
   the frozen `Signal` dataclass with default `None`. Every existing construction
   site (`engine/live.py`, `engine/backtest.py`-adjacent code, both `smoke_test.py`
   and `scanner_test.py`) uses keyword arguments exclusively (verified by
   grepping every `Signal(` call site), so appending a defaulted field is fully
   backward compatible — no other file needs to change.
4. **(Low) Bar-date formatting uses the timestamp object directly.** `Scanner`
   already carries `latest_ts = df.index[-1]` (a `pandas.Timestamp` in every real
   and test data path), which has `.strftime` — no new import needed in
   `engine/scanner.py`.

---

## Task 1: `format_setup_alert_text()` — the label mapping and text builder

**Files:**
- Modify: `signals/detectors.py`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: `signals.detectors.Setup` (existing, unmodified fields), the existing
  module-level `_ROUND_NUMBER_UNIT = 5.0` constant (existing, unmodified).
- Produces: `signals.detectors.format_setup_alert_text(setup: Setup, bar_date: str) -> str`
  — pure function, no I/O. Also produces the module-level `_TRIGGER_LABELS: dict[str, str]`
  and `_CONTEXT_LABELS: dict[str, str]` mappings, consumed only by this function.

- [ ] **Step 1: Write the failing tests**

Open `tests/scanner_test.py`. Add these three functions immediately after
`test_near_round_number` (i.e. right before `def test_near_fvg() -> None:`):

```python
def test_format_setup_alert_text() -> None:
    from signals.detectors import Setup, format_setup_alert_text

    setup = Setup(
        symbol="AAPL",
        triggers=["liquidity_sweep", "bullish_engulfing"],
        context=["uptrend", "near_round_number"],
        price=226.30,
        confluence=4,
    )
    text = format_setup_alert_text(setup, "2026-08-18")

    assert text == (
        "\U0001f50d <b>AAPL</b> \u2014 setup formed, go look\n"
        "<b>Trigger:</b> liquidity sweep + bullish engulfing\n"
        "<b>Context:</b> uptrend, near $225\n"
        "<b>Price:</b> $226.30\n"
        "<b>Bar:</b> 2026-08-18\n"
        "\n"
        "<i>Not a trade signal \u2014 open the chart and decide yourself.</i>"
    )

    print("[ok] format_setup_alert_text")


def test_format_setup_alert_text_no_context() -> None:
    from signals.detectors import Setup, format_setup_alert_text

    setup = Setup(
        symbol="MSFT",
        triggers=["bullish_pin"],
        context=[],
        price=99.99,
        confluence=1,
    )
    text = format_setup_alert_text(setup, "2026-08-18")

    assert "Context:" not in text
    assert text == (
        "\U0001f50d <b>MSFT</b> \u2014 setup formed, go look\n"
        "<b>Trigger:</b> bullish pin\n"
        "<b>Price:</b> $99.99\n"
        "<b>Bar:</b> 2026-08-18\n"
        "\n"
        "<i>Not a trade signal \u2014 open the chart and decide yourself.</i>"
    )

    print("[ok] format_setup_alert_text_no_context")


def test_format_setup_alert_text_emoji_and_no_separators() -> None:
    import re
    import unicodedata

    from signals.detectors import Setup, format_setup_alert_text

    setup = Setup(
        symbol="NVDA",
        triggers=["liquidity_sweep", "bullish_engulfing", "bullish_pin"],
        context=["uptrend", "near_fvg", "near_round_number"],
        price=101.20,
        confluence=6,
    )
    text = format_setup_alert_text(setup, "2026-08-18")

    # Exactly one emoji-category ("So" = Symbol, other) character anywhere in
    # the text, and it must be the single header magnifying-glass -- proves
    # "exactly one emoji, no other emoji anywhere".
    symbol_chars = [ch for ch in text if unicodedata.category(ch) == "So"]
    assert symbol_chars == ["\U0001f50d"]

    # No box-drawing characters (U+2500-U+257F) anywhere.
    assert not any("\u2500" <= ch <= "\u257f" for ch in text)

    # No run of 3+ separator-ish characters (---, ===, ___, repeated dashes) --
    # the two single em-dashes the template itself uses are fine, a *run* of
    # 3+ is what breaks on narrow mobile screens.
    assert re.search(r"[-=_\u2014\u2013]{3,}", text) is None

    print("[ok] format_setup_alert_text_emoji_and_no_separators")
```

Add `test_format_setup_alert_text`, `test_format_setup_alert_text_no_context`,
`test_format_setup_alert_text_emoji_and_no_separators` to the `tests` list inside
`main()`, right after `test_near_round_number,`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m tests.scanner_test`
Expected: FAIL with `ImportError: cannot import name 'format_setup_alert_text' from 'signals.detectors'`

- [ ] **Step 3: Add the label maps and `format_setup_alert_text` to `signals/detectors.py`**

Open `signals/detectors.py`. Find the `Setup` dataclass (it ends with the
`is_actionable` property) and the blank line before `def scan_symbol(`. Insert
this new code between them, i.e. immediately after the `is_actionable` property
and before `def scan_symbol(`:

```python
_TRIGGER_LABELS: dict[str, str] = {
    "liquidity_sweep": "liquidity sweep",
    "bullish_engulfing": "bullish engulfing",
    "bullish_pin": "bullish pin",
}

_CONTEXT_LABELS: dict[str, str] = {
    "uptrend": "uptrend",
    "near_fvg": "near FVG",
}


def format_setup_alert_text(setup: Setup, bar_date: str) -> str:
    """Build the Telegram-visible alert body for a fired Setup.

    This is the single place that translates internal trigger/context keys
    (e.g. "liquidity_sweep") into reader-facing labels. The CSV journal
    (engine/scanner.py's _append_journal) deliberately keeps the raw keys —
    they're better for later filtering/grouping — so only the alert text
    goes through this mapping.
    """
    trigger_text = " + ".join(
        _TRIGGER_LABELS.get(t, t.replace("_", " ")) for t in setup.triggers
    )

    context_labels: list[str] = []
    for c in setup.context:
        if c == "near_round_number":
            nearest = round(setup.price / _ROUND_NUMBER_UNIT) * _ROUND_NUMBER_UNIT
            context_labels.append(f"near ${nearest:,.0f}")
        else:
            context_labels.append(_CONTEXT_LABELS.get(c, c.replace("_", " ")))

    lines = [
        f"\U0001f50d <b>{setup.symbol}</b> \u2014 setup formed, go look",
        f"<b>Trigger:</b> {trigger_text}",
    ]
    if context_labels:
        lines.append(f"<b>Context:</b> {', '.join(context_labels)}")
    lines.append(f"<b>Price:</b> ${setup.price:,.2f}")
    lines.append(f"<b>Bar:</b> {bar_date}")
    lines.append("")
    lines.append("<i>Not a trade signal \u2014 open the chart and decide yourself.</i>")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m tests.scanner_test`
Expected: all `[ok]` lines so far printed, including the three new ones, exit 0.

- [ ] **Step 5: Verify existing smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile signals/detectors.py tests/scanner_test.py
```
Expected: both succeed (no output from `py_compile`, `smoke_test` prints all its
existing `[ok]` lines and exits 0).

- [ ] **Step 6: Commit**

```bash
git add signals/detectors.py tests/scanner_test.py
git commit -m "feat: add format_setup_alert_text for scanner alert bodies"
```

---

## Task 2: `Signal.formatted_text` field + `TelegramAlertSink` override

**Files:**
- Modify: `core/models.py`
- Modify: `alerts/telegram.py`
- Test: `tests/smoke_test.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `core.models.Signal.formatted_text: str | None` (new field, default
  `None`, appended last — every existing call site uses keyword args, so this
  is non-breaking). `alerts.telegram.TelegramAlertSink.send()` now sends
  `signal.formatted_text` verbatim when it is not `None`, otherwise builds the
  exact same generic template as before (unchanged for every existing caller).

- [ ] **Step 1: Write the failing test**

Open `tests/smoke_test.py`. Add this function immediately after
`test_telegram_alert_sink` (i.e. right before `def test_execution_adapter_is_seam_only() -> None:`):

```python
def test_telegram_alert_sink_formatted_text_override() -> None:
    import requests

    from alerts.telegram import TelegramAlertSink
    from core.models import Action, Signal

    sig = Signal(
        symbol="AAPL",
        timestamp="2024-01-02",
        target_position=1,
        action=Action.BUY,
        reason="unused when formatted_text is set",
        price=123.45,
        formatted_text=(
            "\U0001f50d <b>AAPL</b> \u2014 setup formed, go look\n"
            "<i>Not a trade signal \u2014 open the chart and decide yourself.</i>"
        ),
    )

    calls = []

    class _FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post_ok(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return _FakeResponse()

    sink = TelegramAlertSink(token="TOK", chat_id="CHAT")
    orig_post = requests.post
    requests.post = fake_post_ok
    try:
        sink.send(sig)
    finally:
        requests.post = orig_post

    assert len(calls) == 1
    _, payload, _ = calls[0]
    assert payload["text"] == sig.formatted_text
    assert payload["parse_mode"] == "HTML"
    # the generic strategy-alert template must NOT leak through when
    # formatted_text is set
    assert "Reason:" not in payload["text"]
    assert "Signal only" not in payload["text"]

    print("[ok] telegram_alert_sink_formatted_text_override")
```

Add `test_telegram_alert_sink_formatted_text_override` to the `tests` list inside
`main()`, right after `test_telegram_alert_sink,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m tests.smoke_test`
Expected: FAIL with `TypeError: Signal.__init__() got an unexpected keyword argument 'formatted_text'`

- [ ] **Step 3: Add the field to `core/models.py`**

Open `core/models.py`. Find the `Signal` dataclass:

```python
@dataclass(frozen=True)
class Signal:
    symbol: str
    timestamp: object
    target_position: int
    action: Action
    reason: str
    price: float | None
```

Change it to:

```python
@dataclass(frozen=True)
class Signal:
    symbol: str
    timestamp: object
    target_position: int
    action: Action
    reason: str
    price: float | None
    formatted_text: str | None = None
```

- [ ] **Step 4: Run test to verify it now fails differently (formatting not yet wired)**

Run: `python -m tests.smoke_test`
Expected: FAIL — `assert payload["text"] == sig.formatted_text` fails because
`TelegramAlertSink.send` still always builds the generic template.

- [ ] **Step 5: Add the override branch to `alerts/telegram.py`**

Open `alerts/telegram.py`. Find the `send` method:

```python
    def send(self, signal: Signal) -> None:
        emoji = _ACTION_EMOJI.get(signal.action, "")
        text = (
            f"{emoji} <b>{signal.action.value}</b> {signal.symbol}\n"
            f"Price: {signal.price}\n"
            f"Date: {signal.timestamp}\n"
            f"Reason: {signal.reason}\n\n"
            f"<i>Signal only — no order placed.</i>"
        )
        url = self.API_URL.format(token=self.token)
```

Change it to:

```python
    def send(self, signal: Signal) -> None:
        if signal.formatted_text is not None:
            # Pre-built by the caller (e.g. the scanner) -- send verbatim
            # rather than wrapping it in the generic strategy-alert template.
            text = signal.formatted_text
        else:
            emoji = _ACTION_EMOJI.get(signal.action, "")
            text = (
                f"{emoji} <b>{signal.action.value}</b> {signal.symbol}\n"
                f"Price: {signal.price}\n"
                f"Date: {signal.timestamp}\n"
                f"Reason: {signal.reason}\n\n"
                f"<i>Signal only — no order placed.</i>"
            )
        url = self.API_URL.format(token=self.token)
```

The rest of the method (the `requests.post` call and its `try`/`except`) is
unchanged.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m tests.smoke_test`
Expected: all `[ok]` lines so far printed, including
`telegram_alert_sink_formatted_text_override`, exit 0. In particular
`test_telegram_alert_sink` (the pre-existing test, unmodified) must still pass —
it never sets `formatted_text`, so it exercises the `else` branch exactly as
before.

- [ ] **Step 7: Verify scanner tests and compile check are still green**

Run:
```bash
python -m tests.scanner_test
python -m py_compile core/models.py alerts/telegram.py tests/smoke_test.py
```
Expected: both succeed.

- [ ] **Step 8: Commit**

```bash
git add core/models.py alerts/telegram.py tests/smoke_test.py
git commit -m "feat: let Signal carry a pre-built formatted_text for AlertSink"
```

---

## Task 3: Wire the Scanner to produce `formatted_text`

**Files:**
- Modify: `engine/scanner.py`
- Test: `tests/scanner_test.py`

**Interfaces:**
- Consumes: `signals.detectors.format_setup_alert_text` (Task 1),
  `core.models.Signal.formatted_text` (Task 2).
- Produces: `Scanner._to_signal` now returns a `Signal` whose `formatted_text` is
  always populated for every setup the scanner alerts on. `Scanner.reason`
  content is unchanged (see Design Decision 2).

- [ ] **Step 1: Write the failing test**

Open `tests/scanner_test.py`. Add this function immediately after
`test_scanner_alert_on_change_and_state` (i.e. right before
`def test_scanner_journal_failure_preserves_state() -> None:`):

```python
def test_scanner_alert_formatted_text() -> None:
    import os

    from core.config import AppConfig
    from engine.scanner import Scanner

    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    df = pd.DataFrame(
        {
            "open": [105.0, 99.0],
            "high": [106.0, 107.0],
            "low": [99.0, 98.0],
            "close": [100.0, 106.0],
            "volume": [1_000_000] * 2,
        },
        index=idx,
    )  # bar0 bearish, bar1 bullish engulf -> fires with drop_forming_bar=False;
    # only 2 bars -> EMA/ATR warmups never complete, so context is empty here.

    state_path, journal_path = _tmp_path(".json"), _tmp_path(".csv")
    try:
        cfg = AppConfig(state_file=state_path)
        alert = _FakeAlert()
        scanner = Scanner(
            _FakeSource(df),
            alert,
            cfg,
            require_uptrend=False,
            journal_path=journal_path,
            state_path=state_path,
            drop_forming_bar=False,
        )

        setups = scanner.run_once(["AAPL"])
        assert len(setups) == 1
        assert len(alert.sent) == 1

        signal = alert.sent[0]
        text = signal.formatted_text
        assert text is not None
        assert text.startswith("\U0001f50d <b>AAPL</b>")
        assert "bullish engulfing" in text
        assert "Context:" not in text
        assert "Not a trade signal \u2014 open the chart and decide yourself." in text

        # The pre-existing `reason` framing (asserted by
        # test_scanner_alert_on_change_and_state) must be untouched.
        assert "SCANNER: setup formed, go look — not a trade signal." in signal.reason
    finally:
        for p in (state_path, journal_path):
            if os.path.isfile(p):
                os.remove(p)

    print("[ok] scanner_alert_formatted_text")
```

Add `test_scanner_alert_formatted_text` to the `tests` list inside `main()`,
right after `test_scanner_alert_on_change_and_state,`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m tests.scanner_test`
Expected: FAIL — `assert text is not None` fails (`formatted_text` is still
always `None`, since nothing sets it yet).

- [ ] **Step 3: Wire `_to_signal` in `engine/scanner.py`**

Open `engine/scanner.py`. Change the import line:

```python
from signals.detectors import Setup, scan_symbol
```

to:

```python
from signals.detectors import Setup, format_setup_alert_text, scan_symbol
```

Then find `_to_signal`:

```python
    def _to_signal(self, setup: Setup, timestamp) -> Signal:
        reason = (
            "SCANNER: setup formed, go look — not a trade signal. "
            f"triggers={','.join(setup.triggers)} "
            f"context={','.join(setup.context)} "
            f"confluence={setup.confluence}"
        )
        return Signal(
            symbol=setup.symbol,
            timestamp=timestamp,
            target_position=1,
            action=Action.BUY,
            reason=reason,
            price=setup.price,
        )
```

Change it to:

```python
    def _to_signal(self, setup: Setup, timestamp) -> Signal:
        reason = (
            "SCANNER: setup formed, go look — not a trade signal. "
            f"triggers={','.join(setup.triggers)} "
            f"context={','.join(setup.context)} "
            f"confluence={setup.confluence}"
        )
        bar_date = timestamp.strftime("%Y-%m-%d")
        return Signal(
            symbol=setup.symbol,
            timestamp=timestamp,
            target_position=1,
            action=Action.BUY,
            reason=reason,
            price=setup.price,
            formatted_text=format_setup_alert_text(setup, bar_date),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m tests.scanner_test`
Expected: all `[ok]` lines so far printed, including
`scanner_alert_formatted_text`, exit 0.

- [ ] **Step 5: Verify smoke tests and compile check are still green**

Run:
```bash
python -m tests.smoke_test
python -m py_compile engine/scanner.py tests/scanner_test.py
```
Expected: both succeed.

- [ ] **Step 6: Commit**

```bash
git add engine/scanner.py tests/scanner_test.py
git commit -m "feat: wire Scanner alerts to the new formatted_text template"
```

---

## Task 4: Full-suite verification

**Files:** none changed — verification only.

**Interfaces:** none new.

- [ ] **Step 1: Run the full scanner test suite**

Run: `python -m tests.scanner_test`
Expected: exit 0, every `[ok]` line present — the 16 from before this plan plus
the 4 new ones (`format_setup_alert_text`, `format_setup_alert_text_no_context`,
`format_setup_alert_text_emoji_and_no_separators`, `scanner_alert_formatted_text`).

- [ ] **Step 2: Run the full smoke test suite**

Run: `python -m tests.smoke_test`
Expected: exit 0, every pre-existing `[ok]` line still present, plus the new
`telegram_alert_sink_formatted_text_override`. In particular
`test_live_engine`/`test_telegram_alert_sink` must show unchanged behavior —
`live_main.py`'s alert path never sets `formatted_text`, so `TelegramAlertSink`
must still be building the old generic template for it.

- [ ] **Step 3: Compile-check every touched module**

Run:
```bash
python -m py_compile core/models.py alerts/telegram.py signals/detectors.py engine/scanner.py tests/smoke_test.py tests/scanner_test.py
```
Expected: no output, exit 0.

- [ ] **Step 4: Confirm `engine/live.py` and `live_main.py` are byte-for-byte untouched**

Run: `git diff --stat main -- engine/live.py live_main.py`
Expected: empty output (no changes) — this plan is scanner-alert-only per its
Do-NOT list.

- [ ] **Step 5: Report to the user**

Summarize: both test suites green (scanner: 20/20, smoke: 20/20), `py_compile`
clean, `engine/live.py`/`live_main.py` untouched, and restate the "Design
Decisions & Resolved Ambiguities" section above (especially #1, the example's
internal inconsistency) so the user can redirect it if they'd rather hardcode
something closer to the prompt's literal `$225` example.

No commit for this task (verification only).

---

## Self-Review Notes

- **Spec coverage:** every rule in the task's "Rules for the format" section maps
  to an assertion — exactly one emoji + no other emoji
  (`test_format_setup_alert_text_emoji_and_no_separators`), no box-drawing/
  separators (same test), human-readable label mapping incl. computed round-number
  level (`test_format_setup_alert_text`), price/date formatting (same test),
  mandatory closing line present in every case (`test_format_setup_alert_text`,
  `test_format_setup_alert_text_no_context`, `test_scanner_alert_formatted_text`),
  omitted Context line when empty (`test_format_setup_alert_text_no_context`).
- **Do-NOT list respected:** no detector/threshold/invariant touched (Tasks 1-3
  only add a formatter, a dataclass field, and an `if/else` branch); exactly one
  🔍 added and enforced by test; no ASCII art/box-drawing/separators, enforced by
  test; the mandatory line is asserted present in three different tests, never
  optional; `live_main.py`/`engine/live.py` are explicitly verified untouched in
  Task 4 Step 4; no duplicate label-mapping — `_TRIGGER_LABELS`/`_CONTEXT_LABELS`
  exist only in `signals/detectors.py`, and the journal
  (`engine/scanner.py::_append_journal`, unmodified by this plan) keeps writing
  raw keys, exactly as instructed.
- **Type/signature consistency check:** `format_setup_alert_text(setup: Setup, bar_date: str) -> str`
  (Task 1) is called identically in `Scanner._to_signal` (Task 3):
  `format_setup_alert_text(setup, bar_date)` where `bar_date = timestamp.strftime(...)`.
  `Signal.formatted_text: str | None = None` (Task 2) is read identically in
  `TelegramAlertSink.send` (Task 2) and written identically in `Scanner._to_signal`
  (Task 3). No other file constructs a `Signal` with `formatted_text`, so no other
  call site needed updating (verified by grep in Design Decision 3).
