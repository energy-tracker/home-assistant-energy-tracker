"""Parse sensor values using the public API's meter-reading precision."""

from __future__ import annotations

from decimal import ROUND_DOWN, Context, Decimal


def parse_meter_reading_value(raw_state: str) -> Decimal:
    """Preserve decimal digits and truncate to six places within the API range."""
    value = Decimal(raw_state)
    if not value.is_finite() or not 0 <= value < Decimal(10000000000):
        raise ValueError(
            "Meter reading must be finite, non-negative and below 10000000000"
        )
    return value.quantize(
        Decimal("0.000001"), context=Context(prec=16, rounding=ROUND_DOWN)
    )
