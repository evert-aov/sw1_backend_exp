"""Política monetaria compartida por publicación, cotización y reservas."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


@dataclass(frozen=True)
class PriceQuote:
    """Importes de una operación calculados con redondeo por entrada."""

    unit_price: Decimal
    quantity: int
    commission_rate: Decimal
    fee_per_ticket: Decimal
    net_per_ticket: Decimal
    total_amount: Decimal
    platform_fee: Decimal
    host_payout: Decimal
    tier: str


def quote_price(price: Decimal | float | str, quantity: int = 1) -> PriceQuote:
    """Aplica los escalones existentes de la web con Decimal y redondeo HALF_UP."""
    value = Decimal(str(price))
    if not value.is_finite() or value < 0 or quantity < 1:
        raise ValueError("Precio y cantidad inválidos")
    unit = value.quantize(CENT, rounding=ROUND_HALF_UP)
    rate, tier = (Decimal("0.10"), "LOW")
    if unit > 300:
        rate, tier = Decimal("0.05"), "HIGH"
    elif unit >= 100:
        rate, tier = Decimal("0.08"), "MID"
    fee = (unit * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    net = unit - fee
    return PriceQuote(unit, quantity, rate, fee, net, unit * quantity, fee * quantity, net * quantity, tier)
