"""Currency conversion service for the Sellable Potential dashboard.

Reads exchange rates from ``discovery_crm_pricelevels`` (Dynamics 365
convention: rate = base_to_foreign, so converting back to TL means
``amount / rate``). Rates are cached in-process for ``ttl_seconds``.

For TL the rate is treated as 1.0. Missing rates are handled by returning
``None`` from ``to_tl`` so callers can decide whether to drop or warn.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.db.queries import sellable as sq
from app.services.customer_service import CustomerService

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 1800   # 30 minutes


class CurrencyService:
    def __init__(self, customer_service: CustomerService, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._svc = customer_service
        self._ttl = ttl_seconds
        self._rates: dict[str, float] = {"TL": 1.0}
        self._loaded_at: float = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ refresh

    def _is_stale(self) -> bool:
        return (time.time() - self._loaded_at) > self._ttl

    def refresh(self, force: bool = False) -> dict[str, float]:
        """Reload the exchange rate cache from the datalake. Thread-safe."""
        if not force and not self._is_stale():
            return dict(self._rates)
        with self._lock:
            if not force and not self._is_stale():
                return dict(self._rates)
            try:
                with self._svc._get_connection() as conn:
                    with conn.cursor() as cur:
                        rows = self._svc._run_rows(cur, sq.LIST_EXCHANGE_RATES)
            except Exception:  # noqa: BLE001 - defensive
                logger.exception("CurrencyService: failed to refresh exchange rates")
                return dict(self._rates)
            new_rates: dict[str, float] = {"TL": 1.0}
            for row in rows or []:
                ccy, rate = row[0], row[1]
                if not ccy or rate in (None, 0):
                    continue
                try:
                    new_rates[str(ccy).upper()] = float(rate)
                except (TypeError, ValueError):
                    continue
            self._rates = new_rates
            self._loaded_at = time.time()
            logger.info("CurrencyService: refreshed %d rate(s) — %s", len(new_rates), sorted(new_rates))
            return dict(self._rates)

    # ------------------------------------------------------------------ lookup

    def get_rate(self, currency: str | None) -> Optional[float]:
        """Return the cached rate (TL per 1 unit of foreign currency, see to_tl)."""
        if not currency:
            return 1.0
        if self._is_stale():
            self.refresh()
        c = str(currency).upper()
        return self._rates.get(c)

    def to_tl(self, amount: float | int | None, currency: str | None) -> Optional[float]:
        """Convert ``amount`` in ``currency`` into TL.

        Returns ``None`` when the rate is unknown so the caller can warn / skip.

        Dynamics 365 stores ``exchangerate`` as ``foreign_per_base`` (i.e. TL
        per 1 USD = 0.x ish for newer rates; the historical convention used by
        the ICOS export is ``rate = base_per_foreign`` — so dividing yields
        TL). We keep the canonical formula ``tl = amount / rate`` and let the
        operator update rates from the Settings UI when conventions diverge.
        """
        if amount is None:
            return None
        c = (currency or "TL").upper()
        if c == "TL":
            return float(amount)
        rate = self.get_rate(c)
        if not rate or rate == 0:
            return None
        try:
            return float(amount) / float(rate)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
