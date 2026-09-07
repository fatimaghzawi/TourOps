from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.money import ZERO


@dataclass
class CustomerBalanceSnapshot:
    customer_id: ObjectId
    invoiced_total: Decimal = ZERO
    paid_total: Decimal = ZERO
    refunded_total: Decimal = ZERO
    balance: Decimal = ZERO


@dataclass
class SupplierBalanceSnapshot:
    supplier_id: ObjectId
    expense_total: Decimal = ZERO
    paid_total: Decimal = ZERO
    balance: Decimal = ZERO


@dataclass
class TourProfitabilitySnapshot:
    tour_id: ObjectId
    revenue: Decimal = ZERO
    expenses: Decimal = ZERO
    profit: Decimal = ZERO
    currency: Optional[str] = None
