"""Provider nomiga qarab DataProvider instansiyasini qaytaradigan kichik factory."""

from __future__ import annotations

from config.settings import DATA_PROVIDER
from data.alpaca_provider import AlpacaProvider
from data.provider import DataProvider
from data.yfinance_provider import YFinanceProvider

_PROVIDERS: dict[str, type[DataProvider]] = {
    "yfinance": YFinanceProvider,
    "alpaca": AlpacaProvider,
}


def get_provider(name: str | None = None) -> DataProvider:
    """Nomi bo'yicha DataProvider yaratadi (name berilmasa settings.DATA_PROVIDER ishlatiladi)."""
    provider_name = (name or DATA_PROVIDER).lower()
    if provider_name not in _PROVIDERS:
        raise ValueError(f"Noma'lum provider: {provider_name!r}. Mavjudlar: {sorted(_PROVIDERS)}")
    return _PROVIDERS[provider_name]()
