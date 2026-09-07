from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from apps.expenses.constants import CATEGORY_LABELS
from apps.expenses.services import present_expense
from apps.reports.constants import (
    CASH_REFUND_STATUSES,
    EXPENSE_GROUPS,
    EXPENSE_MONEY_FIELDS,
    INVOICE_MONEY_FIELDS,
    LIVE_PAYMENT_STATUSES,
    OPEN_INVOICE_STATUSES,
    REVENUE_INVOICE_STATUSES,
)
from apps.reports.repositories import ReportRepository
from apps.reports.validators import in_range, parse_optional_id, parse_range
from core.constants import BookingStatus, DEFAULT_CURRENCY, ExpenseCategory
from core.exceptions import NotFoundError, ValidationError
from core.money import ZERO, to_money
from core.utils import full_name, serialize_id, utcnow


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _display_date(value) -> str:
    if value is None:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    return str(value)


def _money(document: dict | None, *fields: str) -> dict:
    if not document:
        return {}
    result = dict(document)
    for name in fields:
        if name in result:
            result[name] = to_money(result.get(name))
    return result


def _s(value) -> str:
    return str(to_money(value))


def _pct(part: Decimal, whole: Decimal) -> int:
    if part <= ZERO:
        return 0
    if whole <= ZERO:
        return 100
    return min(int(round(float(part / whole * 100))), 100)


def _margin(profit: Decimal, revenue: Decimal) -> float | None:
    if revenue <= ZERO:
        return None
    return round(float(profit / revenue * 100), 1)


def _party_name(document: dict | None) -> str:
    if not document:
        return "—"
    if document.get("name"):
        return document["name"]
    return full_name(document.get("first_name"), document.get("last_name")) or "—"


def _booking_total(document: dict) -> Decimal:
    pricing = document.get("pricing") or {}
    if isinstance(pricing, dict):
        return to_money(pricing.get("total_amount"))
    return ZERO


def _invoice_remaining(document: dict) -> Decimal:
    if "remaining_amount" in document:
        leftover = to_money(document.get("remaining_amount"))
        return leftover if leftover > ZERO else ZERO
    leftover = to_money(document.get("total_amount")) - to_money(document.get("paid_amount"))
    return leftover if leftover > ZERO else ZERO


def _group_label(category: str) -> str:
    for label, members in EXPENSE_GROUPS:
        if category in members:
            return label
    return "Other"


def serialize_report(payload: dict) -> dict:
    def convert(value):
        if isinstance(value, Decimal):
            return _s(value)
        if hasattr(value, "isoformat") and not isinstance(value, str):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return convert(payload)


class ReportService:
    def __init__(self, repository: ReportRepository | None = None):
        self.repository = repository or ReportRepository()

    def filters(self, params: dict | None = None) -> dict:
        params = params or {}
        start, end = parse_range(
            month=params.get("month"),
            date_from=params.get("from") or params.get("date_from"),
            date_to=params.get("to") or params.get("date_to"),
        )
        tour_id = parse_optional_id(params.get("tour") or params.get("tour_id"), field="tour_id")
        supplier_id = parse_optional_id(params.get("supplier_id"), field="supplier_id")
        customer_id = parse_optional_id(params.get("customer_id"), field="customer_id")
        return {
            "start": start,
            "end": end,
            "tour_id": tour_id,
            "supplier_id": supplier_id,
            "customer_id": customer_id,
            "month": (params.get("month") or "").strip(),
        }

    def tour_options(self) -> list[tuple[str, str]]:
        tours = sorted(self.repository.live(self.repository.tours), key=lambda row: row.get("name") or "")
        return [(str(row["_id"]), row.get("name") or row.get("tour_code") or "Tour") for row in tours]

    def expense_breakdown(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        rows = self._expenses(filters)
        total = sum((to_money(row.get("amount")) for row in rows), ZERO)
        grouped: dict[str, Decimal] = defaultdict(lambda: ZERO)
        by_category: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for row in rows:
            amount = to_money(row.get("amount"))
            category = row.get("category") or ExpenseCategory.OTHER.value
            grouped[_group_label(category)] += amount
            by_category[category] += amount
        order = [label for label, _members in EXPENSE_GROUPS] + ["Other"]
        groups = [
            {
                "label": label,
                "amount": grouped.get(label, ZERO),
                "pct": _pct(grouped.get(label, ZERO), total),
            }
            for label in order
            if grouped.get(label, ZERO) > ZERO
        ]
        categories = [
            {
                "category": key,
                "label": CATEGORY_LABELS.get(key, key.replace("_", " ").title()),
                "amount": amount,
                "pct": _pct(amount, total),
            }
            for key, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True)
        ]
        return self._with_range(
            filters,
            {"total": total, "count": len(rows), "groups": groups, "categories": categories},
        )

    def payables(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        rows = []
        total = ZERO
        for expense in self._expenses(filters):
            remaining = to_money(expense.get("remaining_amount"))
            if remaining <= ZERO:
                continue
            presented = self._present_expense(expense)
            rows.append(presented)
            total += remaining
        rows.sort(key=lambda row: (not row["overdue"], row.get("due") or ""))
        return self._with_range(filters, {"total": total, "count": len(rows), "expenses": rows})

    def receivables(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        rows = []
        total = ZERO
        currencies = set()
        for invoice in self._invoices(filters):
            if invoice.get("status") not in OPEN_INVOICE_STATUSES:
                continue
            remaining = _invoice_remaining(invoice)
            if remaining <= ZERO:
                continue
            presented = self._present_invoice(invoice, remaining=remaining)
            rows.append(presented)
            total += remaining
            currencies.add(invoice.get("currency") or DEFAULT_CURRENCY)
        return self._with_range(
            filters,
            {
                "total": total,
                "count": len(rows),
                "invoices": rows,
                "mixed_currency": len(currencies) > 1,
                "currencies": sorted(currencies),
            },
        )

    def payments(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        rows = [self._present_payment(doc) for doc in self._payments(filters)]
        total = sum((row["amount"] for row in rows), ZERO)
        return self._with_range(filters, {"total": total, "count": len(rows), "payments": rows})

    def refunds(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        docs = self._refunds(filters, cash_only=False)
        rows = [self._present_refund(doc) for doc in docs]
        cash = sum((to_money(doc.get("amount")) for doc in docs if doc.get("status") in CASH_REFUND_STATUSES), ZERO)
        return self._with_range(filters, {"total": cash, "count": len(rows), "refunds": rows})

    def revenue(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        revenue = self._revenue_total(filters)
        costs = sum((to_money(row.get("amount")) for row in self._expenses(filters)), ZERO)
        profit = to_money(revenue - costs)
        return self._with_range(
            filters,
            {
                "revenue": revenue,
                "costs": costs,
                "profit": profit,
                "revenue_pct": 100 if revenue > ZERO else 0,
                "cost_pct": _pct(costs, revenue if revenue > ZERO else costs),
            },
        )

    def profit_loss(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        money_in = sum((to_money(row.get("amount")) for row in self._payments(filters)), ZERO)
        supplier_out = sum((to_money(row.get("amount")) for row in self._supplier_payments(filters)), ZERO)
        refund_out = sum((to_money(row.get("amount")) for row in self._refunds(filters, cash_only=True)), ZERO)
        money_out = to_money(supplier_out + refund_out)
        return self._with_range(
            filters,
            {
                "money_in": money_in,
                "money_out": money_out,
                "supplier_payments": supplier_out,
                "refunds": refund_out,
                "net": to_money(money_in - money_out),
            },
        )

    def transactions(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        rows = []
        for payment in self._payments(filters):
            presented = self._present_payment(payment)
            rows.append(
                {
                    "kind": "PAYMENT",
                    "direction": "IN",
                    "number": presented["number"],
                    "amount": presented["amount"],
                    "signed": presented["amount"],
                    "date": presented["date"],
                    "when": payment.get("payment_date"),
                    "party": presented["customer"],
                    "ref": presented["ref"],
                    "id": presented["id"],
                }
            )
        for refund in self._refunds(filters, cash_only=True):
            presented = self._present_refund(refund)
            rows.append(
                {
                    "kind": "REFUND",
                    "direction": "OUT",
                    "number": presented["number"],
                    "amount": presented["amount"],
                    "signed": to_money(-presented["amount"]),
                    "date": presented["date"],
                    "when": refund.get("processed_at") or refund.get("created_at"),
                    "party": presented["customer"],
                    "ref": presented["reason"],
                    "id": presented["id"],
                }
            )
        for payment in self._supplier_payments(filters):
            presented = self._present_supplier_payment(payment)
            rows.append(
                {
                    "kind": "SUPPLIER_PAYMENT",
                    "direction": "OUT",
                    "number": presented["number"],
                    "amount": presented["amount"],
                    "signed": to_money(-presented["amount"]),
                    "date": presented["date"],
                    "when": payment.get("payment_date"),
                    "party": presented["supplier"],
                    "ref": presented["ref"],
                    "id": presented["id"],
                }
            )
        rows.sort(key=lambda row: (row.get("when") is None, row.get("when")), reverse=True)
        money_in = sum((row["amount"] for row in rows if row["direction"] == "IN"), ZERO)
        money_out = sum((row["amount"] for row in rows if row["direction"] == "OUT"), ZERO)
        return self._with_range(
            filters,
            {
                "transactions": rows,
                "count": len(rows),
                "money_in": money_in,
                "money_out": money_out,
                "net": to_money(money_in - money_out),
            },
        )

    def tour_profitability(self, params: dict | None = None) -> dict:
        filters = self.filters(params)
        selected_id = filters.get("tour_id")
        table_filters = dict(filters)
        table_filters["tour_id"] = None
        snapshots = self._tour_snapshots(table_filters)
        selected = None
        if selected_id:
            selected = next((row for row in snapshots if row["id"] == str(selected_id)), None)
            if selected is None:
                tour = self._lookup_tour(str(selected_id))
                if not tour:
                    raise NotFoundError("Tour not found.")
                selected = {
                    "id": str(selected_id),
                    "name": tour.get("name") or tour.get("tour_code") or "Tour",
                    "status": tour.get("status"),
                    "revenue": ZERO,
                    "supplier_costs": ZERO,
                    "other_costs": ZERO,
                    "costs": ZERO,
                    "profit": ZERO,
                    "margin": None,
                    "categories": [],
                    "currency": tour.get("currency") or DEFAULT_CURRENCY,
                }
                snapshots.append(selected)
        profitable = [row for row in snapshots if row["margin"] is not None]
        top = sorted(profitable, key=lambda row: -(row["margin"] or 0))[:5]
        low = sorted(profitable, key=lambda row: row["margin"] or 0)[:5]
        totals = {
            "revenue": sum((row["revenue"] for row in snapshots), ZERO),
            "supplier_costs": sum((row["supplier_costs"] for row in snapshots), ZERO),
            "other_costs": sum((row["other_costs"] for row in snapshots), ZERO),
            "costs": sum((row["costs"] for row in snapshots), ZERO),
            "profit": sum((row["profit"] for row in snapshots), ZERO),
        }
        totals["margin"] = _margin(totals["profit"], totals["revenue"])
        overhead = sum(
            (to_money(row.get("amount")) for row in self._expenses(table_filters) if not row.get("tour_id")),
            ZERO,
        )
        totals["other_costs"] = to_money(totals["other_costs"] + overhead)
        totals["costs"] = to_money(totals["supplier_costs"] + totals["other_costs"])
        totals["profit"] = to_money(totals["revenue"] - totals["costs"])
        totals["margin"] = _margin(totals["profit"], totals["revenue"])
        basis = totals["revenue"] if totals["revenue"] > ZERO else (totals["costs"] if totals["costs"] > ZERO else Decimal("1"))
        totals["revenue_pct"] = 100 if totals["revenue"] > ZERO else 0
        totals["supplier_pct"] = _pct(totals["supplier_costs"], basis)
        totals["other_pct"] = _pct(totals["other_costs"], basis)
        totals["profit_pct"] = _pct(totals["profit"], basis) if totals["profit"] > ZERO else 0
        return self._with_range(
            filters,
            {
                "tours": snapshots,
                "top": top,
                "low": low,
                "totals": totals,
                "overhead": overhead,
                "selected": selected,
            },
        )

    def _tour_snapshots(self, filters: dict) -> list[dict]:
        tours = {_id_str(row["_id"]): row for row in self.repository.live(self.repository.tours)}
        revenue_by_tour: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for tour_id, amount in self._revenue_by_tour(filters).items():
            revenue_by_tour[tour_id] += amount
        costs_by_tour: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"supplier": ZERO, "other": ZERO, "categories": defaultdict(lambda: ZERO)}
        )
        for expense in self._expenses(filters):
            if not expense.get("tour_id"):
                continue
            tour_id = _id_str(expense["tour_id"])
            amount = to_money(expense.get("amount"))
            if expense.get("supplier_id"):
                costs_by_tour[tour_id]["supplier"] += amount
            else:
                costs_by_tour[tour_id]["other"] += amount
            category = expense.get("category") or ExpenseCategory.OTHER.value
            costs_by_tour[tour_id]["categories"][category] += amount

        ids = set(revenue_by_tour) | set(costs_by_tour)
        if filters.get("tour_id"):
            ids.add(str(filters["tour_id"]))
        snapshots = []
        for tour_id in ids:
            tour = tours.get(tour_id) or self._lookup_tour(tour_id)
            name = (tour or {}).get("name") or (tour or {}).get("tour_code")
            if not name:
                name = "Unassigned" if tour_id == "unassigned" else "Tour"
            revenue = revenue_by_tour.get(tour_id, ZERO)
            buckets = costs_by_tour.get(tour_id) or {"supplier": ZERO, "other": ZERO, "categories": {}}
            supplier_costs = to_money(buckets["supplier"])
            other_costs = to_money(buckets["other"])
            costs = to_money(supplier_costs + other_costs)
            profit = to_money(revenue - costs)
            categories = [
                {
                    "category": key,
                    "label": CATEGORY_LABELS.get(key, key.replace("_", " ").title()),
                    "amount": amount,
                    "pct": _pct(amount, costs),
                }
                for key, amount in sorted((buckets.get("categories") or {}).items(), key=lambda item: item[1], reverse=True)
            ]
            snapshots.append(
                {
                    "id": tour_id,
                    "name": name,
                    "status": (tour or {}).get("status"),
                    "revenue": revenue,
                    "supplier_costs": supplier_costs,
                    "other_costs": other_costs,
                    "costs": costs,
                    "profit": profit,
                    "margin": _margin(profit, revenue),
                    "categories": categories,
                    "currency": (tour or {}).get("currency") or DEFAULT_CURRENCY,
                }
            )
        snapshots.sort(key=lambda row: row["profit"], reverse=True)
        return snapshots

    def _lookup_tour(self, tour_id: str) -> dict | None:
        try:
            return self.repository.find(self.repository.tours, tour_id)
        except ValidationError:
            return None

    def _revenue_total(self, filters: dict) -> Decimal:
        return sum(self._revenue_by_tour(filters).values(), ZERO)

    def _revenue_by_tour(self, filters: dict) -> dict[str, Decimal]:
        invoices = self.repository.live(self.repository.invoices)
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        if invoices:
            bookings = {_id_str(row["_id"]): row for row in self.repository.live(self.repository.bookings)}
            for invoice in invoices:
                hydrated = _money(invoice, *INVOICE_MONEY_FIELDS)
                if hydrated.get("status") not in REVENUE_INVOICE_STATUSES:
                    continue
                if not in_range(hydrated.get("issue_date"), filters["start"], filters["end"]):
                    continue
                if filters.get("customer_id") and hydrated.get("customer_id") != filters["customer_id"]:
                    continue
                booking = bookings.get(_id_str(hydrated.get("booking_id"))) if hydrated.get("booking_id") else None
                tour_id = _id_str((booking or {}).get("tour_id")) if booking else None
                if filters.get("tour_id") and tour_id != str(filters["tour_id"]):
                    continue
                totals[tour_id or "unassigned"] += to_money(hydrated.get("total_amount")) - to_money(
                    hydrated.get("refunded_amount")
                )
            return totals
        for booking in self.repository.live(self.repository.bookings):
            if booking.get("booking_status") not in {BookingStatus.CONFIRMED.value, BookingStatus.COMPLETED.value}:
                continue
            if not in_range(booking.get("booking_date"), filters["start"], filters["end"]):
                continue
            if filters.get("customer_id") and booking.get("customer_id") != filters["customer_id"]:
                continue
            tour_id = _id_str(booking.get("tour_id"))
            if filters.get("tour_id") and tour_id != str(filters["tour_id"]):
                continue
            totals[tour_id or "unassigned"] += _booking_total(booking)
        return totals

    def _expenses(self, filters: dict) -> list[dict]:
        rows = []
        for document in self.repository.live(self.repository.expenses):
            hydrated = _money(document, *EXPENSE_MONEY_FIELDS)
            if not in_range(hydrated.get("expense_date"), filters["start"], filters["end"]):
                continue
            if filters.get("tour_id") and _id_str(hydrated.get("tour_id")) != str(filters["tour_id"]):
                continue
            if filters.get("supplier_id") and hydrated.get("supplier_id") != filters["supplier_id"]:
                continue
            rows.append(hydrated)
        return rows

    def _invoices(self, filters: dict) -> list[dict]:
        rows = []
        for document in self.repository.live(self.repository.invoices):
            hydrated = _money(document, *INVOICE_MONEY_FIELDS)
            if not in_range(hydrated.get("issue_date"), filters["start"], filters["end"]):
                continue
            if filters.get("customer_id") and hydrated.get("customer_id") != filters["customer_id"]:
                continue
            rows.append(hydrated)
        return rows

    def _payments(self, filters: dict) -> list[dict]:
        rows = []
        for document in self.repository.live(self.repository.payments):
            hydrated = _money(document, "amount")
            status = hydrated.get("status") or "COMPLETED"
            if status not in LIVE_PAYMENT_STATUSES:
                continue
            if not in_range(hydrated.get("payment_date"), filters["start"], filters["end"]):
                continue
            if filters.get("customer_id") and hydrated.get("customer_id") != filters["customer_id"]:
                continue
            rows.append(hydrated)
        return rows

    def _refunds(self, filters: dict, *, cash_only: bool) -> list[dict]:
        rows = []
        for document in self.repository.live(self.repository.refunds):
            hydrated = _money(document, "amount")
            if cash_only and hydrated.get("status") not in CASH_REFUND_STATUSES:
                continue
            when = hydrated.get("processed_at") or hydrated.get("created_at")
            if not in_range(when, filters["start"], filters["end"]):
                continue
            if filters.get("customer_id") and hydrated.get("customer_id") != filters["customer_id"]:
                continue
            rows.append(hydrated)
        return rows

    def _supplier_payments(self, filters: dict) -> list[dict]:
        rows = []
        for document in self.repository.live(self.repository.supplier_payments):
            hydrated = _money(document, "amount")
            if not in_range(hydrated.get("payment_date"), filters["start"], filters["end"]):
                continue
            if filters.get("supplier_id") and hydrated.get("supplier_id") != filters["supplier_id"]:
                continue
            if filters.get("tour_id"):
                expense = self.repository.find(self.repository.expenses, hydrated.get("expense_id")) if hydrated.get("expense_id") else None
                if not expense or _id_str(expense.get("tour_id")) != str(filters["tour_id"]):
                    continue
            rows.append(hydrated)
        return rows

    def _present_expense(self, document: dict) -> dict:
        supplier = None
        tour = None
        if document.get("supplier_id"):
            supplier = self.repository.find(self.repository.suppliers, document["supplier_id"])
        if document.get("tour_id"):
            try:
                tour = self.repository.find(self.repository.tours, document["tour_id"])
            except ValidationError:
                tour = None
        presented = present_expense(document, supplier=supplier, tour=tour)
        return presented

    def _present_invoice(self, document: dict, *, remaining: Decimal) -> dict:
        customer = None
        if document.get("customer_id"):
            try:
                customer = self.repository.find(self.repository.customers, document["customer_id"])
            except ValidationError:
                customer = None
        due = document.get("due_date")
        overdue = False
        if remaining > ZERO and due is not None:
            due_day = due.date() if hasattr(due, "date") else due
            overdue = due_day < utcnow().date()
        return {
            "id": str(document["_id"]),
            "number": document.get("invoice_number") or "",
            "customer": _party_name(customer),
            "customer_id": serialize_id(document.get("customer_id")),
            "due": _display_date(due),
            "due_date": due,
            "remaining": remaining,
            "total": to_money(document.get("total_amount")),
            "status": document.get("status"),
            "currency": document.get("currency") or DEFAULT_CURRENCY,
            "has_remaining": remaining > ZERO,
            "overdue": overdue,
        }

    def _present_payment(self, document: dict) -> dict:
        customer = None
        if document.get("customer_id"):
            try:
                customer = self.repository.find(self.repository.customers, document["customer_id"])
            except ValidationError:
                customer = None
        return {
            "id": str(document["_id"]),
            "number": document.get("payment_number") or "",
            "amount": to_money(document.get("amount")),
            "method": document.get("payment_method"),
            "date": _display_date(document.get("payment_date")),
            "payment_date": document.get("payment_date"),
            "customer": _party_name(customer),
            "customer_id": serialize_id(document.get("customer_id")),
            "ref": document.get("reference_number") or "",
            "status": document.get("status") or "COMPLETED",
        }

    def _present_refund(self, document: dict) -> dict:
        customer = None
        if document.get("customer_id"):
            try:
                customer = self.repository.find(self.repository.customers, document["customer_id"])
            except ValidationError:
                customer = None
        when = document.get("processed_at") or document.get("created_at")
        return {
            "id": str(document["_id"]),
            "number": document.get("refund_number") or "",
            "amount": to_money(document.get("amount")),
            "status": document.get("status"),
            "date": _display_date(when),
            "customer": _party_name(customer),
            "customer_id": serialize_id(document.get("customer_id")),
            "reason": document.get("reason") or "",
        }

    def _present_supplier_payment(self, document: dict) -> dict:
        supplier = None
        if document.get("supplier_id"):
            try:
                supplier = self.repository.find(self.repository.suppliers, document["supplier_id"])
            except ValidationError:
                supplier = None
        return {
            "id": str(document["_id"]),
            "number": document.get("supplier_payment_number") or "",
            "amount": to_money(document.get("amount")),
            "date": _display_date(document.get("payment_date")),
            "supplier": _party_name(supplier),
            "supplier_id": serialize_id(document.get("supplier_id")),
            "ref": document.get("reference_number") or "",
        }

    def _with_range(self, filters: dict, payload: dict) -> dict:
        payload["from"] = filters.get("start")
        payload["to"] = filters.get("end")
        payload["month"] = filters.get("month") or ""
        payload["tour_id"] = serialize_id(filters.get("tour_id"))
        return payload


def _id_str(value) -> str | None:
    if value is None:
        return None
    return str(value)
