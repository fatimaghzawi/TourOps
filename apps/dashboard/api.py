from apps.finance.services import FinanceService
from apps.reports.services import serialize_report
from core.http import guarded, query_filters
from core.responses import success_response


@guarded
def accountant(request, **kwargs):
    return success_response(serialize_report(FinanceService().accountant_dashboard(query_filters(request))))


@guarded
def owner(request, **kwargs):
    return success_response(serialize_report(FinanceService().owner_dashboard(query_filters(request))))
