from apps.expenses.services import ExpenseService, serialize_expense
from core.http import actor_id, guarded, json_body, query_value, resource_id
from core.responses import success_response


def _presented(expense) -> dict:
    return serialize_expense(ExpenseService().get_presented(expense["_id"], include_payments=True))


@guarded
def list_expenses(request, **kwargs):
    overdue_raw = query_value(request, "overdue")
    items = ExpenseService().list_presented(
        category=query_value(request, "category"),
        payment_status=query_value(request, "payment_status", "status"),
        expense_scope=query_value(request, "expense_scope", "scope"),
        supplier_id=query_value(request, "supplier_id"),
        tour_id=query_value(request, "tour_id"),
        overdue=True if overdue_raw and str(overdue_raw).lower() in {"1", "true", "yes"} else None,
    )
    return success_response({"expenses": [serialize_expense(item) for item in items]})


@guarded
def create_expense(request, **kwargs):
    payload = json_body(request)
    expense = ExpenseService().create(
        actor_id=actor_id(request),
        expense_scope=payload.get("expense_scope") or payload.get("scope") or "",
        category=payload.get("category") or "",
        amount=payload.get("amount"),
        description=payload.get("description") or "",
        expense_date=payload.get("expense_date"),
        currency=payload.get("currency"),
        supplier_id=payload.get("supplier_id"),
        tour_id=payload.get("tour_id"),
        due_date=payload.get("due_date"),
        receipt_file=payload.get("receipt_file"),
    )
    return success_response(_presented(expense), status=201)


@guarded
def get_expense(request, **kwargs):
    record = ExpenseService().get_presented(resource_id(kwargs), include_payments=True)
    return success_response(serialize_expense(record))


@guarded
def patch_expense(request, **kwargs):
    payload = json_body(request)
    changes = {
        key: payload[key]
        for key in (
            "expense_scope",
            "category",
            "amount",
            "description",
            "expense_date",
            "currency",
            "supplier_id",
            "tour_id",
            "due_date",
            "receipt_file",
        )
        if key in payload
    }
    if "scope" in payload and "expense_scope" not in changes:
        changes["expense_scope"] = payload["scope"]
    expense = ExpenseService().update(resource_id(kwargs), actor_id=actor_id(request), **changes)
    return success_response(_presented(expense))


@guarded
def expenses_for_tour(request, **kwargs):
    items = ExpenseService().list_for_tour(resource_id(kwargs, "id", "tour_id"))
    return success_response({"expenses": [serialize_expense(item) for item in items]})


@guarded
def expenses_for_supplier(request, **kwargs):
    items = ExpenseService().list_for_supplier(resource_id(kwargs, "id", "supplier_id"))
    return success_response({"expenses": [serialize_expense(item) for item in items]})
