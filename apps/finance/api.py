from apps.finance.services import FinanceService
from apps.reports.services import serialize_report
from core.http import guarded, query_filters, resource_id
from core.responses import success_response


def _ok(payload: dict):
    return success_response(serialize_report(payload))


@guarded
def receivables(request, **kwargs):
    return _ok(FinanceService().receivables(query_filters(request)))


@guarded
def payables(request, **kwargs):
    return _ok(FinanceService().payables(query_filters(request)))


@guarded
def customer_balances(request, **kwargs):
    return _ok(FinanceService().customer_balances(query_filters(request)))


@guarded
def supplier_balances(request, **kwargs):
    return _ok(FinanceService().supplier_balances(query_filters(request)))


@guarded
def customer_balance(request, **kwargs):
    return _ok(
        FinanceService().customer_balance(
            resource_id(kwargs, "id", "customer_id"),
            query_filters(request),
        )
    )


@guarded
def supplier_balance(request, **kwargs):
    return _ok(
        FinanceService().supplier_balance(
            resource_id(kwargs, "id", "supplier_id"),
            query_filters(request),
        )
    )


@guarded
def tour_profitability(request, **kwargs):
    return _ok(
        FinanceService().tour_profitability(
            resource_id(kwargs, "id", "tour_id"),
            query_filters(request),
        )
    )
