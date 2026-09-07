import pytest

from core.money import to_decimal, to_decimal128, to_money


def test_money_from_string():
    assert to_money("10.1") == to_decimal("10.10")


def test_decimal128_roundtrip():
    stored = to_decimal128("19.99")
    assert to_decimal(stored) == to_money("19.99")


def test_rejects_float():
    with pytest.raises(TypeError):
        to_decimal(1.2)
