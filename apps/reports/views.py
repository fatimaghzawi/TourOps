from django.contrib import messages
from django.shortcuts import render

from apps.reports.forms import ReportFilterForm
from apps.reports.services import ReportService
from core.access import REPORT_ROLES
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import login_required, role_required


def _params(request) -> dict:
    return {
        "month": request.GET.get("month") or "",
        "from": request.GET.get("from") or request.GET.get("date_from") or "",
        "to": request.GET.get("to") or request.GET.get("date_to") or "",
        "tour": request.GET.get("tour") or request.GET.get("tour_id") or "",
        "customer_id": request.GET.get("customer_id") or "",
        "supplier_id": request.GET.get("supplier_id") or "",
    }


def _query(params: dict) -> str:
    parts = []
    for key in ("month", "from", "to", "tour", "customer_id", "supplier_id"):
        if params.get(key):
            parts.append(f"{key}={params[key]}")
    return ("?" + "&".join(parts)) if parts else ""


def _context(request, *, title, heading, extra=None):
    service = ReportService()
    params = _params(request)
    try:
        tours = service.tour_options()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Reports are unavailable.")
        tours = []
    form = ReportFilterForm(
        initial={
            "month": params["month"],
            "date_from": params["from"] or None,
            "date_to": params["to"] or None,
            "tour_id": params["tour"],
        },
        tour_choices=tours,
    )
    payload = {
        "page_title": title,
        "page_heading": heading,
        "form": form,
        "filters": params,
        "query": _query(params),
        "tour_choices": tours,
    }
    if extra:
        payload.update(extra)
    return payload


def _report(request, *, title, heading, builder, template, with_tour=True):
    service = ReportService()
    params = _params(request)
    try:
        report = builder(service, params)
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Reports are unavailable.")
        report = None
    except TourOpsError as extra:
        messages.error(request, extra.message)
        report = None
    ctx = _context(
        request,
        title=title,
        heading=heading,
        extra={"report": report},
    )
    if not with_tour:
        ctx["tour_choices"] = None
    return render(request, template, ctx)


@login_required
@role_required(*REPORT_ROLES)
def report_list(request):
    service = ReportService()
    params = _params(request)
    try:
        summary = {
            "revenue": service.revenue(params),
            "cash": service.profit_loss(params),
            "receivables": service.receivables(params),
            "payables": service.payables(params),
        }
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Reports are unavailable.")
        summary = None
    except TourOpsError as extra:
        messages.error(request, extra.message)
        summary = None
    ctx = _context(request, title="Reports", heading="Financial reports", extra={"summary": summary})
    return render(request, "reports/list.html", ctx)


@login_required
@role_required(*REPORT_ROLES)
def report_revenue(request):
    return _report(
        request,
        title="Revenue vs cost",
        heading="Revenue vs cost",
        builder=lambda service, params: service.revenue(params),
        template="reports/revenue.html",
    )


@login_required
@role_required(*REPORT_ROLES)
def report_expenses(request):
    return _report(
        request,
        title="Expense breakdown",
        heading="Expense breakdown",
        builder=lambda service, params: service.expense_breakdown(params),
        template="reports/expenses.html",
    )


@login_required
@role_required(*REPORT_ROLES)
def report_profit_loss(request):
    return _report(
        request,
        title="Cash flow",
        heading="Cash flow",
        builder=lambda service, params: service.profit_loss(params),
        template="reports/profit_loss.html",
        with_tour=False,
    )


@login_required
@role_required(*REPORT_ROLES)
def tour_profitability(request):
    service = ReportService()
    params = _params(request)
    try:
        report = service.tour_profitability(params)
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Reports are unavailable.")
        report = None
    except TourOpsError as extra:
        messages.error(request, extra.message)
        report = None
    selected = (report or {}).get("selected") if report else None
    ctx = _context(
        request,
        title="Tour profitability",
        heading="Tour profitability",
        extra={"report": report, "selected": selected},
    )
    return render(request, "reports/profitability.html", ctx)


@login_required
@role_required(*REPORT_ROLES)
def report_payments(request):
    return _report(
        request,
        title="Payments report",
        heading="Customer payments",
        builder=lambda service, params: service.payments(params),
        template="reports/payments.html",
        with_tour=False,
    )


@login_required
@role_required(*REPORT_ROLES)
def report_refunds(request):
    return _report(
        request,
        title="Refunds report",
        heading="Refunds",
        builder=lambda service, params: service.refunds(params),
        template="reports/refunds.html",
        with_tour=False,
    )


@login_required
@role_required(*REPORT_ROLES)
def report_transactions(request):
    return _report(
        request,
        title="Transactions",
        heading="Cash ledger",
        builder=lambda service, params: service.transactions(params),
        template="reports/transactions.html",
        with_tour=False,
    )
