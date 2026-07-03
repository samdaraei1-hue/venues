from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PriceBreakdown:
    nightly_total: float | None
    per_person_total: float | None
    estimated_total: float | None


def estimate_total_cost(
    *,
    price_per_night: float | None = None,
    price_per_person: float | None = None,
    guest_count: int | None = None,
    cleaning_fee: float | None = None,
    security_deposit: float | None = None,
) -> PriceBreakdown:
    nightly_total = price_per_night
    per_person_total = None
    estimated_total = None

    if price_per_person is not None and guest_count is not None:
        per_person_total = price_per_person * guest_count
        estimated_total = per_person_total
    elif nightly_total is not None:
        estimated_total = nightly_total

    extras = [value for value in (cleaning_fee, security_deposit) if value is not None]
    if estimated_total is not None:
        estimated_total += sum(extras)

    return PriceBreakdown(
        nightly_total=nightly_total,
        per_person_total=per_person_total,
        estimated_total=estimated_total,
    )

