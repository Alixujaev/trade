"""paper/seal.py: time-locked sealing of performance-bearing outputs (protocol 2.3 E7). Standard library only.

Construction: random 16-byte nonce; keystream = HMAC-SHA256(enc_key, nonce || counter) blocks (CTR mode); tag =
HMAC-SHA256(mac_key, nonce || ciphertext) (encrypt-then-MAC); enc_key / mac_key derived from the 32-byte seal key
by HMAC with distinct labels. `unseal` refuses before SEAL_UNTIL and on a bad tag (constant-time compare).

The time lock is enforced in code; custody of the key (secret PAPER_SEAL_KEY) is procedural: whoever holds the key could
decrypt with other tools. Unsealing before SEAL_UNTIL is a protocol breach (artifacts/day27/protocol-v2.3-amendment.md).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets

from paper.config import SEAL_UNTIL

MAGIC = b"PSEAL1"


class SealError(RuntimeError):
    pass


def load_key(env: str = "PAPER_SEAL_KEY") -> bytes:
    raw = os.environ.get(env, "")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise SealError(f"{env} is not hex") from None
    if len(key) != 32:
        raise SealError(f"{env} must be 32 bytes (64 hex characters)")
    return key


def new_key_hex() -> str:
    return secrets.token_hex(32)


def _subkeys(key: bytes) -> tuple[bytes, bytes]:
    return (hmac.new(key, b"paper-seal-enc", hashlib.sha256).digest(),
            hmac.new(key, b"paper-seal-mac", hashlib.sha256).digest())


def _keystream(k_enc: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    ctr = 0
    while len(out) < n:
        out += hmac.new(k_enc, nonce + ctr.to_bytes(8, "big"), hashlib.sha256).digest()
        ctr += 1
    return bytes(out[:n])


def seal(plain: bytes, key: bytes) -> bytes:
    k_enc, k_mac = _subkeys(key)
    nonce = secrets.token_bytes(16)
    ct = bytes(a ^ b for a, b in zip(plain, _keystream(k_enc, nonce, len(plain))))
    tag = hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()
    return MAGIC + nonce + tag + ct


def unseal(blob: bytes, key: bytes, now: datetime | None = None) -> bytes:
    now = now or datetime.now(timezone.utc)
    if now < SEAL_UNTIL:
        raise SealError(f"sealed until {SEAL_UNTIL.isoformat()} (protocol 2.3 E7); refusing to reveal")
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 48:
        raise SealError("not a sealed blob")
    nonce, tag, ct = blob[6:22], blob[22:54], blob[54:]
    k_enc, k_mac = _subkeys(key)
    if not hmac.compare_digest(tag, hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()):
        raise SealError("authentication tag mismatch (wrong key or tampered blob)")
    return bytes(a ^ b for a, b in zip(ct, _keystream(k_enc, nonce, len(ct))))
