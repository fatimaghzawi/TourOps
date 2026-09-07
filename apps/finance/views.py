from django.contrib import messages
from django.shortcuts import render

from apps.finance.services import FinanceService
from apps.reports.services import ReportService
from core.access import FINANCE_ROLES
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


def _page(request, *, title, heading, lead, report, active, template):
    params = _params(request)
    try:
        tours = ReportService().tour_options()
    except DatabaseUnavailableError:
        tours = []
    return render(
        request,
        template,
        {
            "page_title": title,
            "page_heading": heading,
            "lead": lead,
            "report": report,
            "filters": params,
            "query": _query(params),
            "tour_choices": tours,
            "finance_tab": active,
        },
    )


def _load(builder, params):
    try:
        return builder(params), None
    except DatabaseUnavailableError:
        return None, "Cannot reach MongoDB. Business finance is unavailable."
    except TourOpsError as extra:
        return None, extra.message


@login_required
@role_required(*FINANCE_ROLES)
def receivables(request):
    params = _params(request)
    report, error = _load(FinanceService().receivables, params)
    if error:
        messages.error(request, error)
    return _page(
        request,
        title="Accounts receivable",
        heading="Accounts receivable",
        lead="Open customer invoices still waiting to be collected.",
        report=report,
        active="receivables",
        template="finance/receivables.html",
    )


@login_required
@role_required(*FINANCE_ROLES)
def payables(request):
    params = _params(request)
    report, error = _load(FinanceService().payables, params)
    if error:
        messages.error(request, error)
    return _page(
        request,
        title="Accounts payable",
        heading="Accounts payable",
        lead="Open supplier expenses waiting to be paid.",
        report=report,
        active="payables",
        template="finance/payables.html",
    )


@login_required
@role_required(*FINANCE_ROLES)
def customer_balances(request):
    params = _params(request)
    report, error = _load(FinanceService().customer_balances, params)
    if error:
        messages.error(request, error)
    return _page(
        request,
        title="Customer balances",
        heading="Customer balances",
        lead="Outstanding AR rolled up by customer. Calculated live — not stored.",
        report=report,
        active="customers",
        template="finance/customer_balances.html",
    )


@login_required
@role_required(*FINANCE_ROLES)
def supplier_balances(request):
    params = _params(request)
    report, error = _load(FinanceService().supplier_balances, params)
    if error:
        messages.error(request, error)
    return _page(
        request,
        title="Supplier balances",
        heading="Supplier balances",
        lead="Outstanding AP rolled up by supplier. Calculated live — not stored.",
        report=report,
        active="suppliers",
        template="finance/supplier_balances.html",
    )
