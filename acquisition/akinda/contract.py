"""acquisition/akinda/contract.py: pinned Akinda /compliance contract (vendor docs https://b2b.akinda.io/developer/docs,
read 2026-10-17; evidence in docs/shariah/AKINDA_PROVIDER_DECISION.md).

Documented /compliance fields: ticker ("Uppercase ticker symbol echoed back from the request"), company_name,
halal_status, listing_country, reporting_currency, last_scanned ("When the Shariah audit last ran for this ticker.
null means never audited"), last_updated (market-data refresh; NOT a screening date). Example date format
"Aug 06, 2026". Documented statuses: HALAL, NOT HALAL, DOUBTFUL, UNQUALIFIED, ERROR_DATA, INCOMPLETE_DATA.
Anything else is unrecognised and never tradable.
"""

from __future__ import annotations

from datetime import timedelta
import re
from typing import Final

from acquisition.contract import ROOT_DIR

PROVIDER: Final[str] = "Akinda B2B API v1"
SOURCE: Final[str] = "Akinda B2B API v1 /compliance"
BASE_URL: Final[str] = "https://b2b-api.akinda.io/api/v1"
API_KEY_ENV: Final[str] = "AKINDA_API_KEY"
API_KEY_HEADER: Final[str] = "X-API-Key"                 # header only; the documented ?apikey= form is never used

DAILY_CALL_LIMIT: Final[int] = 10                        # Basic plan, /compliance "10 / day" (reset time undocumented)
QUOTA_WINDOW: Final[timedelta] = timedelta(hours=24)     # rolling window: conservative for any reset time
MAX_ATTEMPTS_PER_TICKER: Final[int] = 2                  # 5xx / network only; 401/403/429 are never retried
RETRY_SLEEP_S: Final[float] = 5.0
TIMEOUT_S: Final[float] = 30.0

STATUS_HALAL: Final[str] = "HALAL"
STATUS_NOT_HALAL: Final[str] = "NOT HALAL"
NO_VERDICT_STATUSES: Final[frozenset[str]] = frozenset({"DOUBTFUL", "UNQUALIFIED", "ERROR_DATA", "INCOMPLETE_DATA"})
REQUIRED_FIELDS: Final[tuple[str, ...]] = ("ticker", "halal_status", "last_scanned")
LAST_SCANNED_FORMAT: Final[str] = "%b %d, %Y"            # documented example "Aug 06, 2026"; no other format guessed

REVIEWER: Final[str] = "akinda-sync (automated; owner provider decision D13-A)"
DEFAULT_EVIDENCE_ROOT: Final = ROOT_DIR / "screening_evidence" / "akinda"     # git-ignored
PROTECTED_ROOTS: Final = (ROOT_DIR / "data", ROOT_DIR / "artifacts", ROOT_DIR / "paper_state")
TICKER_RE: Final = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
