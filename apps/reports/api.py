from apps.reports.services import ReportService, serialize_report
from core.http import guarded, query_filters
from core.responses import success_response


def _report(builder):
    @guarded
    def view(request, **kwargs):
        return success_response(serialize_report(builder(ReportService(), query_filters(request))))

    return view


revenue = _report(lambda service, params: service.revenue(params))
expenses = _report(lambda service, params: service.expense_breakdown(params))
payments = _report(lambda service, params: service.payments(params))
refunds = _report(lambda service, params: service.refunds(params))
receivables = _report(lambda service, params: service.receivables(params))
payables = _report(lambda service, params: service.payables(params))
tour_profitability = _report(lambda service, params: service.tour_profitability(params))
profit_loss = _report(lambda service, params: service.profit_loss(params))
transactions = _report(lambda service, params: service.transactions(params))
