from __future__ import annotations

from apps.finance.services import FinanceService
from apps.reports.services import ReportService
from core.money import ZERO, to_money


def _overdue_total(rows: list[dict]):
    return sum((to_money(row.get("remaining")) for row in rows), ZERO)


class DashboardService:
    def __init__(
        self,
        finance: FinanceService | None = None,
        reports: ReportService | None = None,
    ):
        self.finance = finance or FinanceService()
        self.reports = reports or ReportService()

    def accountant(self, params: dict | None = None) -> dict:
        params = params or {}
        summary = self.finance.accountant_dashboard(params)
        receivables = self.reports.receivables(params)
        payables = self.reports.payables(params)
        transactions = self.reports.transactions(params)
        overdue_invoices = [row for row in (receivables.get("invoices") or []) if row.get("overdue")]
        overdue_expenses = [row for row in (payables.get("expenses") or []) if row.get("overdue")]
        open_invoices = (receivables.get("invoices") or [])[:5]
        open_expenses = (payables.get("expenses") or [])[:5]
        return {
            "summary": summary,
            "receivables": receivables,
            "payables": payables,
            "overdue_invoices": overdue_invoices[:5],
            "overdue_expenses": overdue_expenses[:5],
            "overdue_ar_count": len(overdue_invoices),
            "overdue_ap_count": len(overdue_expenses),
            "overdue_ar_total": _overdue_total(overdue_invoices),
            "overdue_ap_total": _overdue_total(overdue_expenses),
            "open_invoices": open_invoices,
            "open_expenses": open_expenses,
            "recent": (transactions.get("transactions") or [])[:8],
        }

    def owner(self, params: dict | None = None) -> dict:
        payload = self.accountant(params)
        revenue = self.reports.revenue(params)
        profitability = self.reports.tour_profitability(params)
        sold = to_money(revenue.get("revenue"))
        profit = to_money(revenue.get("profit"))
        payload.update(
            {
                "revenue": revenue,
                "profitability": profitability,
                "top_tours": (profitability.get("top") or [])[:5],
                "low_tours": (profitability.get("low") or [])[:5],
                "margin_pct": int(round(float(profit / sold * 100))) if sold > ZERO else 0,
            }
        )
        return payload
