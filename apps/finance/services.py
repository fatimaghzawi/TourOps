from __future__ import annotations

from apps.reports.services import ReportService
from apps.suppliers.services import SupplierService
from apps.tours.services import TourService
from core.money import ZERO, to_money
from core.utils import parse_object_id


class FinanceService:
    def __init__(self, reports: ReportService | None = None):
        self.reports = reports or ReportService()

    def receivables(self, params: dict | None = None) -> dict:
        return self.reports.receivables(params)

    def payables(self, params: dict | None = None) -> dict:
        return self.reports.payables(params)

    def customer_balance(self, customer_id: str, params: dict | None = None) -> dict:
        parse_object_id(customer_id, field="customer_id")
        filters = dict(params or {})
        filters["customer_id"] = customer_id
        report = self.reports.receivables(filters)
        return {
            "customer_id": customer_id,
            "outstanding": report.get("total"),
            "count": report.get("count"),
            "invoices": report.get("invoices") or [],
            "from": report.get("from"),
            "to": report.get("to"),
            "month": report.get("month") or "",
        }

    def supplier_balance(self, supplier_id: str, params: dict | None = None) -> dict:
        SupplierService().get(supplier_id)
        filters = dict(params or {})
        filters["supplier_id"] = supplier_id
        report = self.reports.payables(filters)
        return {
            "supplier_id": supplier_id,
            "outstanding": report.get("total"),
            "count": report.get("count"),
            "expenses": report.get("expenses") or [],
            "from": report.get("from"),
            "to": report.get("to"),
            "month": report.get("month") or "",
        }

    def customer_balances(self, params: dict | None = None) -> dict:
        report = self.reports.receivables(params)
        grouped: dict[str, dict] = {}
        for invoice in report.get("invoices") or []:
            key = invoice.get("customer_id") or "unknown"
            bucket = grouped.setdefault(
                key,
                {
                    "customer_id": invoice.get("customer_id"),
                    "customer": invoice.get("customer"),
                    "outstanding": ZERO,
                    "count": 0,
                    "overdue": False,
                },
            )
            bucket["outstanding"] = to_money(bucket["outstanding"] + to_money(invoice.get("remaining")))
            bucket["count"] += 1
            bucket["overdue"] = bucket["overdue"] or bool(invoice.get("overdue"))
        rows = sorted(grouped.values(), key=lambda row: row["outstanding"], reverse=True)
        return {
            "total": report.get("total"),
            "count": len(rows),
            "customers": rows,
            "from": report.get("from"),
            "to": report.get("to"),
            "month": report.get("month") or "",
        }

    def supplier_balances(self, params: dict | None = None) -> dict:
        report = self.reports.payables(params)
        grouped: dict[str, dict] = {}
        for expense in report.get("expenses") or []:
            key = expense.get("supplier_id") or "unknown"
            bucket = grouped.setdefault(
                key,
                {
                    "supplier_id": expense.get("supplier_id"),
                    "supplier": expense.get("supplier"),
                    "outstanding": ZERO,
                    "count": 0,
                    "overdue": False,
                },
            )
            bucket["outstanding"] = to_money(bucket["outstanding"] + to_money(expense.get("remaining")))
            bucket["count"] += 1
            bucket["overdue"] = bucket["overdue"] or bool(expense.get("overdue"))
        rows = sorted(grouped.values(), key=lambda row: row["outstanding"], reverse=True)
        return {
            "total": report.get("total"),
            "count": len(rows),
            "suppliers": rows,
            "from": report.get("from"),
            "to": report.get("to"),
            "month": report.get("month") or "",
        }

    def tour_profitability(self, tour_id: str, params: dict | None = None) -> dict:
        TourService().get(tour_id)
        filters = dict(params or {})
        filters["tour_id"] = tour_id
        return self.reports.tour_profitability(filters)

    def accountant_dashboard(self, params: dict | None = None) -> dict:
        receivables = self.reports.receivables(params)
        payables = self.reports.payables(params)
        cash = self.reports.profit_loss(params)
        return {
            "receivables": {"total": receivables.get("total"), "count": receivables.get("count")},
            "payables": {"total": payables.get("total"), "count": payables.get("count")},
            "money_in": cash.get("money_in"),
            "money_out": cash.get("money_out"),
            "net": cash.get("net"),
            "from": cash.get("from"),
            "to": cash.get("to"),
            "month": cash.get("month") or "",
        }

    def owner_dashboard(self, params: dict | None = None) -> dict:
        summary = self.accountant_dashboard(params)
        revenue = self.reports.revenue(params)
        profitability = self.reports.tour_profitability(params)
        totals = profitability.get("totals") or {}
        summary.update(
            {
                "revenue": revenue.get("revenue"),
                "costs": revenue.get("costs"),
                "profit": revenue.get("profit"),
                "tour_profit": totals.get("profit"),
            }
        )
        return summary
