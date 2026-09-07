from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from core.constants import CostBasis, SupplierServiceKind
from core.exceptions import ValidationError
from core.money import ZERO, to_money

DEFAULT_MARGIN = Decimal("30.00")
MAX_MARGIN = Decimal("80.00")

BASIS_LABELS = {
    CostBasis.PER_PERSON.value: "per traveler",
    CostBasis.PER_GROUP.value: "for the departure",
}

COSTING_MONEY_KEYS = (
    "variable_per_person",
    "group_total",
    "land_cost_per_person",
    "suggested_price",
    "selling_price",
    "profit_per_person",
    "profit_at_capacity",
    "land_cost_at_booked",
    "profit_at_booked",
)


def default_cost_basis(service_kind: str | None = None) -> str:
    kind = (service_kind or "").strip().upper()
    if kind == SupplierServiceKind.ACCOMMODATION.value:
        return CostBasis.PER_PERSON.value
    return CostBasis.PER_GROUP.value


def parse_cost_basis(value, *, service_kind: str | None = None, strict: bool = False) -> str:
    raw = (str(value).strip().upper() if value not in (None, "") else "")
    allowed = {item.value for item in CostBasis}
    if raw in allowed:
        return raw
    if not raw:
        return default_cost_basis(service_kind)
    if strict:
        raise ValidationError("Cost must be per traveler or for the whole departure.")
    return default_cost_basis(service_kind)


def parse_margin_percent(value) -> Decimal:
    if value in (None, ""):
        return DEFAULT_MARGIN
    try:
        margin = to_money(value)
    except (TypeError, ValueError) as extra:
        raise ValidationError("Invalid target margin.") from extra
    if margin < ZERO or margin > MAX_MARGIN:
        raise ValidationError("Target margin must be between 0 and 80%.")
    return margin


def commercial_price(amount) -> Decimal:
    value = to_money(amount)
    if value <= ZERO:
        return ZERO
    tens = (value / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_CEILING)
    return to_money(tens * Decimal("10"))


def cost_sheet(
    services,
    *,
    capacity: int,
    selling_price=None,
    margin_percent=None,
    booked: int = 0,
) -> dict:
    seats = max(int(capacity or 0), 1)
    sold = max(int(booked or 0), 0)
    margin = parse_margin_percent(margin_percent)
    variable = ZERO
    group = ZERO
    lines = []
    for line in services or []:
        if not isinstance(line, dict):
            continue
        amount = to_money(line.get("estimated_cost"))
        basis = parse_cost_basis(line.get("cost_basis"), service_kind=line.get("service_kind"))
        if basis == CostBasis.PER_PERSON.value:
            share = amount
            variable += amount
        else:
            share = to_money(amount / Decimal(seats))
            group += amount
        lines.append(
            {
                "name": line.get("name") or line.get("title") or line.get("description") or "Service",
                "supplier": line.get("supplier") or line.get("supplier_name") or "",
                "estimated_cost": amount,
                "cost_basis": basis,
                "basis_label": BASIS_LABELS[basis],
                "per_person_share": share,
            }
        )
    land = to_money(variable + (group / Decimal(seats)))
    suggested_raw = ZERO
    leftover = Decimal("1") - (margin / Decimal("100"))
    if land > ZERO and leftover > ZERO:
        suggested_raw = land / leftover
    suggested = commercial_price(suggested_raw)
    if selling_price in (None, ""):
        selling = suggested
    else:
        selling = to_money(selling_price)
    profit_pp = to_money(selling - land)
    margin_on_price = round(float(profit_pp / selling * 100), 1) if selling > ZERO else None
    contribution = selling - variable
    break_even = None
    if group > ZERO and contribution > ZERO:
        break_even = int((group / contribution).to_integral_value(rounding=ROUND_CEILING))
    elif group <= ZERO and selling > variable:
        break_even = 1
    booked_land = None
    booked_profit = None
    if sold > 0:
        booked_land = to_money(variable + (group / Decimal(sold)))
        booked_profit = to_money((selling * Decimal(sold)) - (variable * Decimal(sold) + group))
    return {
        "lines": lines,
        "capacity": seats,
        "booked": sold,
        "variable_per_person": to_money(variable),
        "group_total": to_money(group),
        "land_cost_per_person": land,
        "target_margin_percent": margin,
        "suggested_price": suggested,
        "selling_price": selling,
        "profit_per_person": profit_pp,
        "margin_percent": margin_on_price if margin_on_price is not None else 0,
        "profit_at_capacity": to_money(profit_pp * Decimal(seats)),
        "break_even_pax": break_even,
        "below_cost": selling > ZERO and selling < land,
        "has_costs": bool(lines) and (land > ZERO or group > ZERO or variable > ZERO),
        "land_cost_at_booked": booked_land,
        "profit_at_booked": booked_profit,
    }


def serialize_costing(sheet: dict | None) -> dict | None:
    if not sheet:
        return None
    payload = dict(sheet)
    for key in COSTING_MONEY_KEYS:
        if isinstance(payload.get(key), Decimal):
            payload[key] = str(to_money(payload[key]))
    if isinstance(payload.get("target_margin_percent"), Decimal):
        payload["target_margin_percent"] = str(to_money(payload["target_margin_percent"]))
    lines = []
    for line in payload.get("lines") or []:
        row = dict(line)
        for money_key in ("estimated_cost", "per_person_share"):
            if isinstance(row.get(money_key), Decimal):
                row[money_key] = str(to_money(row[money_key]))
        lines.append(row)
    payload["lines"] = lines
    return payload
