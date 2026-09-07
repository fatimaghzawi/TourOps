from __future__ import annotations

from django.urls import reverse

from apps.presentation.constants import STAGES


def _u(name, **kwargs):
    try:
        return reverse(name, kwargs=kwargs) if kwargs else reverse(name)
    except Exception:
        return "/"


def _pane(path: str, label: str = "") -> dict:
    return {"path": path, "label": label}


def _paths(story: dict) -> dict:
    tour = story.get("tour_id") or ""
    package = story.get("package_id") or ""
    hotel_res = story.get("hotel_res_id") or ""
    hotel_expense = story.get("hotel_expense_id") or ""
    tour_path = _u("tours:detail", id=tour) if tour else _u("tours:list")

    def tab(name):
        return f"{tour_path}?tab={name}" if tour else tour_path

    return {
        "agent-home": _u("dashboard:agent"),
        "suppliers": _u("suppliers:list"),
        "services": _u("suppliers:services"),
        "package": _u("packages:detail", id=package) if package else _u("packages:list"),
        "tours": _u("tours:list"),
        "tour": tab("overview"),
        "gallery": tab("gallery"),
        "reservations": tab("reservations"),
        "email": _u("supplier_reservations:email", id=hotel_res) if hotel_res else tab("reservations"),
        "maya": _u("customers:create"),
        "booking": f"{_u('bookings:create')}?tour_id={tour}" if tour else _u("bookings:create"),
        "invoices": _u("invoices:list"),
        "refunds": [
            _pane(_u("refunds:list"), "Open refunds"),
            _pane(_u("refunds:create"), "Ask for a refund"),
        ],
        "accountant-home": _u("dashboard:accountant"),
        "pay-partial": [
            _pane(f"{_u('invoices:list')}?status=ISSUED", "Still due"),
            _pane(_u("payments:create"), "Take a partial"),
        ],
        "pay-full": [
            _pane(f"{_u('invoices:list')}?status=PAID", "Paid in full"),
            _pane(_u("payments:list"), "The ledger"),
        ],
        "receipts": _u("receipts:list"),
        "expenses": _u("expenses:list"),
        "supplier-pay": (
            f"{_u('supplier_payments:create')}?expense_id={hotel_expense}"
            if hotel_expense
            else _u("supplier_payments:create")
        ),
        "receivables": [
            _pane(_u("finance:receivables"), "Who owes us"),
            _pane(_u("finance:customer_balances"), "Customer balances"),
        ],
        "payables": [
            _pane(_u("finance:payables"), "What we owe"),
            _pane(_u("finance:supplier_balances"), "Supplier balances"),
        ],
        "owner-home": _u("dashboard:owner"),
        "profit": f"{_u('reports:profitability')}?tour={tour}" if tour else _u("reports:profitability"),
        "pnl": _u("reports:profit_loss"),
        "reports": [
            _pane(_u("reports:revenue"), "Revenue"),
            _pane(_u("reports:payments"), "Payments in"),
        ],
        "transactions": _u("reports:transactions"),
    }


def scenes_for(story: dict | None = None) -> list[dict]:
    paths = _paths(story or {})
    rows = [
        {"id": "agent-home", "stage": "agent", "title": "The desk that sells the departure"},
        {"id": "suppliers", "stage": "agent", "title": "Hotel, transport, and guide on file"},
        {"id": "services", "stage": "agent", "title": "What they actually sell us"},
        {"id": "package", "stage": "agent", "title": "Istanbul Escape as a reusable product"},
        {"id": "tours", "stage": "agent", "title": "The departure with photos on the board"},
        {"id": "tour", "stage": "agent", "title": "A dated departure with a seat ceiling"},
        {"id": "gallery", "stage": "agent", "title": "Walk the client through the city"},
        {"id": "reservations", "stage": "agent", "title": "Hold the hotel, coach, and guide"},
        {"id": "email", "stage": "agent", "title": "Ask the hotel in writing"},
        {"id": "maya", "stage": "agent", "title": "A traveler walks in"},
        {"id": "booking", "stage": "agent", "title": "Book two seats and invoice together"},
        {"id": "invoices", "stage": "agent", "title": "The invoice the desk just created"},
        {"id": "refunds", "stage": "agent", "title": "If the trip falls through, the desk starts the refund"},
        {"id": "accountant-home", "stage": "accountant", "title": "Cash, not inventory"},
        {"id": "pay-partial", "stage": "accountant", "title": "Collect a deposit — partial payment"},
        {"id": "pay-full", "stage": "accountant", "title": "Then collect the balance — paid in full"},
        {"id": "receipts", "stage": "accountant", "title": "A receipt for every payment"},
        {"id": "expenses", "stage": "accountant", "title": "The tour still has to be paid for"},
        {"id": "supplier-pay", "stage": "accountant", "title": "Pay the hotel from the expense"},
        {"id": "receivables", "stage": "accountant", "title": "Who still owes the agency"},
        {"id": "payables", "stage": "accountant", "title": "What the agency still owes"},
        {"id": "owner-home", "stage": "owner", "title": "The whole chain on one desk"},
        {"id": "profit", "stage": "owner", "title": "Did this departure make money?"},
        {"id": "pnl", "stage": "owner", "title": "Profit and loss, not a guess"},
        {"id": "reports", "stage": "owner", "title": "Revenue beside money actually received"},
        {"id": "transactions", "stage": "owner", "title": "Every movement on the books"},
    ]
    labels = {"agent": "Agent", "accountant": "Accountant", "owner": "Owner"}
    for row in rows:
        target = paths.get(row["id"], "/")
        if isinstance(target, list):
            row["panes"] = target
        else:
            row["panes"] = [_pane(target)]
        count = len(row["panes"])
        row["layout"] = "fan" if count >= 3 else "overlap" if count == 2 else "one"
        row["role"] = labels.get(row["stage"], row["stage"])
    return rows


def stage_index(stage: str) -> int:
    order = [item[0] for item in STAGES]
    try:
        return order.index(stage)
    except ValueError:
        return 0


def first_scene_for_stage(stage: str) -> int:
    for index, scene in enumerate(scenes_for()):
        if scene["stage"] == stage:
            return index
    return 0
