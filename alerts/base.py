from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import Signal


class AlertSink(ABC):
    @abstractmethod
    def send(self, signal: Signal) -> None:
        raise NotImplementedError
