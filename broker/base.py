from __future__ import annotations

from abc import ABC, abstractmethod


class ExecutionAdapter(ABC):
    """Seam for order execution (Phase 3, §17). No implementation in v1.0 (INV-9)."""

    @abstractmethod
    def submit_order(self, symbol: str, target_position: int) -> None:
        raise NotImplementedError
