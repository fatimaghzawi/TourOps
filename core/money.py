from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

from bson.decimal128 import Decimal128

TWOPLACE = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, float):
        raise TypeError(
            "Refusing to convert float to money. Pass Decimal, str, int, or Decimal128."
        )
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


def to_money(value: Any) -> Decimal:
    return to_decimal(value).quantize(TWOPLACE, rounding=ROUND_HALF_UP)


def to_decimal128(value: Any) -> Decimal128:
    return Decimal128(str(to_money(value)))


def money_dict(document: dict, *field_names: str) -> dict:
    result = dict(document)
    for name in field_names:
        if name in result and result[name] is not None:
            result[name] = to_decimal(result[name])
    return result
