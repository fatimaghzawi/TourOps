from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.expenses.repositories import ExpenseRepository
from apps.expenses.schemas import ExpenseDocument
from apps.expenses.validators import (
    parse_money,
    parse_optional_object_id,
    parse_positive_money,
    parse_when,
    payment_status_for,
    remaining_for,
    validate_category,
    validate_scope,
)
from apps.notifications.constants import NotificationType
from apps.notifications.services import FINANCE_NOTIFY_ROLES, safe_notify_roles
from core.constants import Collections, DEFAULT_CURRENCY, ExpenseCategory, ExpenseScope, TourStatus
from core.exceptions import BusinessRuleViolation, DatabaseUnavailableError, NotFoundError, ValidationError
from core.money import ZERO, to_decimal128, to_money
from core.numbering import next_number
from core.utils import parse_object_id, serialize_id, utcnow


SUPPLIER_REQUIRED_CATEGORIES = {
    ExpenseCategory.HOTEL.value,
    ExpenseCategory.TRANSPORTATION.value,
    ExpenseCategory.TOUR_GUIDE.value,
    ExpenseCategory.FLIGHT.value,
    ExpenseCategory.ACTIVITY.value,
}


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


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def is_overdue(document: dict, *, today=None) -> bool:
    due = document.get("due_date")
    remaining = to_money(document.get("remaining_amount"))
    if due is None or remaining <= ZERO:
        return False
    due_day = _as_date(due)
    check = today or utcnow().date()
    return due_day < check


def present_expense(
    document: dict,
    *,
    supplier: dict | None = None,
    tour: dict | None = None,
    payments: list[dict] | None = None,
) -> dict:
    amount = to_money(document.get("amount"))
    paid = to_money(document.get("paid_amount"))
    remaining = to_money(document.get("remaining_amount"))
    supplier_name = (supplier or {}).get("name") if supplier else None
    tour_name = (tour or {}).get("name") if tour else None
    presented_payments = [present_supplier_payment(item) for item in (payments or [])]
    return {
        "id": str(document["_id"]),
        "number": document.get("expense_number") or "",
        "expense_number": document.get("expense_number") or "",
        "expense_scope": document.get("expense_scope"),
        "scope": document.get("expense_scope"),
        "category": document.get("category"),
        "amount": amount,
        "paid": paid,
        "remaining": remaining,
        "currency": document.get("currency") or DEFAULT_CURRENCY,
        "description": document.get("description") or "",
        "expense_date": document.get("expense_date"),
        "expense_date_display": _display_date(document.get("expense_date")),
        "due_date": document.get("due_date"),
        "due": _display_date(document.get("due_date")),
        "created_by": serialize_id(document.get("created_by")),
        "supplier_id": serialize_id(document.get("supplier_id")),
        "supplier": supplier_name or "—",
        "tour_id": serialize_id(document.get("tour_id")),
        "related": tour_name or ("General" if document.get("expense_scope") == ExpenseScope.GENERAL.value else "—"),
        "payment_status": document.get("payment_status"),
        "status": document.get("payment_status"),
        "receipt_file": document.get("receipt_file"),
        "overdue": is_overdue(document),
        "has_remaining": remaining > ZERO,
        "has_payments": paid > ZERO,
        "payments": presented_payments,
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def present_supplier_payment(document: dict) -> dict:
    amount = to_money(document.get("amount"))
    return {
        "id": str(document["_id"]),
        "number": document.get("supplier_payment_number") or "",
        "amount": amount,
        "method": document.get("payment_method"),
        "date": _display_date(document.get("payment_date")),
        "payment_date": document.get("payment_date"),
        "ref": document.get("reference_number") or "",
        "notes": document.get("notes") or "",
        "expense_id": serialize_id(document.get("expense_id")),
    }


def serialize_expense(presented: dict) -> dict:
    payload = dict(presented)
    for key in ("amount", "paid", "remaining"):
        if isinstance(payload.get(key), Decimal):
            payload[key] = str(to_money(payload[key]))
    for key in ("expense_date", "due_date", "created_at", "updated_at"):
        payload[key] = _iso(payload.get(key))
    payload["payments"] = [
        {
            **item,
            "amount": str(to_money(item["amount"])) if isinstance(item.get("amount"), Decimal) else item.get("amount"),
            "payment_date": _iso(item.get("payment_date")),
        }
        for item in payload.get("payments") or []
    ]
    return payload


class ExpenseService:
    def __init__(self, repository: ExpenseRepository | None = None):
        self.repository = repository or ExpenseRepository()

    def list_items(self, **filters) -> list[dict]:
        extra = self._mongo_filters(**filters)
        documents = self.repository.list_expenses(extra)
        if filters.get("overdue"):
            documents = [doc for doc in documents if is_overdue(doc)]
        return documents

    def list_presented(self, **filters) -> list[dict]:
        return [self._present(doc) for doc in self.list_items(**filters)]

    def get(self, expense_id) -> dict:
        try:
            document = self.repository.find_by_id(expense_id)
        except ValidationError as exc:
            raise NotFoundError("Expense not found.") from exc
        if not document:
            raise NotFoundError("Expense not found.")
        return document

    def get_presented(self, expense_id, *, include_payments: bool = True) -> dict:
        return self._present(self.get(expense_id), include_payments=include_payments)

    def create(
        self,
        *,
        actor_id,
        expense_scope: str,
        category: str,
        amount,
        description: str,
        expense_date,
        currency: str | None = None,
        supplier_id=None,
        tour_id=None,
        due_date=None,
        receipt_file: str | None = None,
    ) -> dict:
        scope = validate_scope(expense_scope)
        category = validate_category(category)
        money = parse_positive_money(amount, field="amount")
        description = (description or "").strip()
        if not description:
            raise ValidationError("Description is required.")
        when = parse_when(expense_date, field="expense_date")
        due = parse_when(due_date, field="due_date", required=False)
        currency = (currency or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        if len(currency) != 3:
            raise ValidationError("Currency must be a 3-letter code.")
        supplier_oid = parse_optional_object_id(supplier_id, field="supplier_id")
        tour_oid = parse_optional_object_id(tour_id, field="tour_id")
        receipt_file = (receipt_file or "").strip() or None

        if supplier_oid and not self.repository.find_supplier(supplier_oid):
            raise ValidationError("Supplier not found.")
        if scope == ExpenseScope.GENERAL.value:
            tour_oid = None
        else:
            if not tour_oid:
                raise ValidationError("A tour is required for tour-scoped expenses.")
            tour = self.repository.find_tour(tour_oid)
            if not tour:
                raise ValidationError("Tour not found.")
            if tour.get("status") == TourStatus.CANCELLED.value:
                raise BusinessRuleViolation("Cannot post expenses against a cancelled tour.")
        if category in SUPPLIER_REQUIRED_CATEGORIES and not supplier_oid:
            raise ValidationError("A supplier is required for this expense category.")
        if due and when and _as_date(due) < _as_date(when):
            raise ValidationError("Due date cannot be before the expense date.")

        now = utcnow()
        document = {
            "expense_number": next_number(Collections.EXPENSES),
            "expense_scope": scope,
            "category": category,
            "amount": to_decimal128(money),
            "currency": currency,
            "description": description,
            "expense_date": when,
            "created_by": parse_object_id(actor_id, field="created_by"),
            "created_at": now,
            "updated_at": now,
            "supplier_id": supplier_oid,
            "tour_id": tour_oid,
            "due_date": due,
            "paid_amount": to_decimal128(ZERO),
            "remaining_amount": to_decimal128(money),
            "payment_status": payment_status_for(money, ZERO),
            "receipt_file": receipt_file,
        }
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as exc:
            raise ValidationError("An expense with this number already exists.") from exc
        except PyMongoError as exc:
            raise DatabaseUnavailableError("Could not save the expense.") from exc
        document["_id"] = result.inserted_id
        saved = self.get(document["_id"])
        number = saved.get("expense_number") or ""
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.CREATED.value,
            entity_type="expenses",
            entity_id=saved["_id"],
            description=f"Created expense {number}.",
            after={"expense_number": number, "amount": str(to_money(saved.get("amount"))), "category": saved.get("category")},
        )
        safe_notify_roles(
            FINANCE_NOTIFY_ROLES,
            type=NotificationType.EXPENSE.value,
            title=f"Expense {number}",
            message=f"A new {saved.get('category', 'expense').replace('_', ' ').lower()} expense was recorded.",
            related_entity_type="expenses",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def update(self, expense_id, *, actor_id=None, **changes) -> dict:
        document = self.get(expense_id)
        paid = to_money(document.get("paid_amount"))
        updates = {}

        if "expense_scope" in changes and changes["expense_scope"] is not None:
            updates["expense_scope"] = validate_scope(changes["expense_scope"])
        scope = updates.get("expense_scope", document.get("expense_scope"))

        if "category" in changes and changes["category"] is not None:
            updates["category"] = validate_category(changes["category"])
        if "description" in changes and changes["description"] is not None:
            description = (changes["description"] or "").strip()
            if not description:
                raise ValidationError("Description is required.")
            updates["description"] = description
        if "currency" in changes and changes["currency"] is not None:
            currency = (changes["currency"] or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
            if len(currency) != 3:
                raise ValidationError("Currency must be a 3-letter code.")
            updates["currency"] = currency
        if "receipt_file" in changes:
            updates["receipt_file"] = (changes["receipt_file"] or "").strip() or None
        if "expense_date" in changes and changes["expense_date"] is not None:
            updates["expense_date"] = parse_when(changes["expense_date"], field="expense_date")
        if "due_date" in changes:
            updates["due_date"] = parse_when(changes["due_date"], field="due_date", required=False)

        if "supplier_id" in changes:
            supplier_oid = parse_optional_object_id(changes["supplier_id"], field="supplier_id")
            if supplier_oid and not self.repository.find_supplier(supplier_oid):
                raise ValidationError("Supplier not found.")
            updates["supplier_id"] = supplier_oid

        if "tour_id" in changes or "expense_scope" in changes:
            tour_oid = parse_optional_object_id(
                changes["tour_id"] if "tour_id" in changes else document.get("tour_id"),
                field="tour_id",
            )
            if scope == ExpenseScope.GENERAL.value:
                updates["tour_id"] = None
            else:
                if not tour_oid:
                    raise ValidationError("A tour is required for tour-scoped expenses.")
                tour = self.repository.find_tour(tour_oid)
                if not tour:
                    raise ValidationError("Tour not found.")
                if tour.get("status") == TourStatus.CANCELLED.value:
                    raise BusinessRuleViolation("Cannot post expenses against a cancelled tour.")
                updates["tour_id"] = tour_oid

        if "amount" in changes and changes["amount"] is not None:
            if paid > ZERO:
                raise ValidationError("Cannot change the amount of an expense that already has supplier payments.")
            amount = parse_positive_money(changes["amount"], field="amount")
            remaining = remaining_for(amount, paid)
            updates["amount"] = to_decimal128(amount)
            updates["remaining_amount"] = to_decimal128(remaining)
            updates["payment_status"] = payment_status_for(amount, paid)

        if "paid_amount" in changes:
            raise ValidationError("Paid amount is updated through supplier payments.")

        if not updates:
            return document
        expense_date = updates.get("expense_date", document.get("expense_date"))
        due_date = updates["due_date"] if "due_date" in updates else document.get("due_date")
        if due_date and expense_date and _as_date(due_date) < _as_date(expense_date):
            raise ValidationError("Due date cannot be before the expense date.")
        category = updates.get("category", document.get("category"))
        supplier_id = updates["supplier_id"] if "supplier_id" in updates else document.get("supplier_id")
        if category in SUPPLIER_REQUIRED_CATEGORIES and not supplier_id:
            raise ValidationError("A supplier is required for this expense category.")
        updates["updated_at"] = utcnow()
        try:
            self.repository.update(document["_id"], updates)
        except PyMongoError as exc:
            raise DatabaseUnavailableError("Could not update the expense.") from exc
        saved = self.get(document["_id"])
        number = saved.get("expense_number") or document.get("expense_number") or ""
        safe_audit(
            actor_id=actor_id or document.get("created_by"),
            action=AuditAction.UPDATED.value,
            entity_type="expenses",
            entity_id=saved["_id"],
            description=f"Updated expense {number}.",
            after={"fields": sorted(k for k in updates.keys() if k != "updated_at")},
        )
        return saved

    def sync_paid_amount(self, expense_id, paid_amount) -> dict:
        document = self.get(expense_id)
        amount = to_money(document.get("amount"))
        paid = parse_money(paid_amount, field="paid_amount")
        remaining = remaining_for(amount, paid)
        try:
            self.repository.update(
                document["_id"],
                {
                    "paid_amount": to_decimal128(paid),
                    "remaining_amount": to_decimal128(remaining),
                    "payment_status": payment_status_for(amount, paid),
                    "updated_at": utcnow(),
                },
            )
        except PyMongoError as exc:
            raise DatabaseUnavailableError("Could not update the expense balance.") from exc
        return self.get(document["_id"])

    def soft_delete(self, expense_id, *, actor_id) -> None:
        document = self.get(expense_id)
        if to_money(document.get("paid_amount")) > ZERO:
            raise ValidationError("Cannot delete an expense that already has supplier payments.")
        try:
            result = self.repository.soft_delete(document["_id"], actor_id)
        except PyMongoError as exc:
            raise DatabaseUnavailableError("Could not delete the expense.") from exc
        if result.matched_count != 1:
            raise NotFoundError("Expense not found.")
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.DELETED.value,
            entity_type="expenses",
            entity_id=document["_id"],
            description=f"Deleted expense {document.get('expense_number') or ''}.",
            before={"expense_number": document.get("expense_number")},
        )

    def list_for_tour(self, tour_id) -> list[dict]:
        tour = self.repository.find_tour(tour_id)
        if not tour:
            raise NotFoundError("Tour not found.")
        return self.list_presented(tour_id=tour["_id"])

    def list_for_supplier(self, supplier_id) -> list[dict]:
        supplier = self.repository.find_supplier(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found.")
        return self.list_presented(supplier_id=supplier["_id"])

    def list_supplier_options(self) -> list[tuple[str, str]]:
        return [(str(doc["_id"]), doc.get("name") or doc.get("supplier_number") or "Supplier") for doc in self.repository.list_suppliers()]

    def list_tour_options(self) -> list[tuple[str, str]]:
        return [(str(doc["_id"]), doc.get("name") or doc.get("tour_code") or "Tour") for doc in self.repository.list_tours()]

    def _present(self, document: dict, *, include_payments: bool = False) -> dict:
        supplier = None
        tour = None
        payments = None
        if document.get("supplier_id"):
            supplier = self.repository.find_supplier(document["supplier_id"])
        if document.get("tour_id"):
            tour = self.repository.find_tour(document["tour_id"])
        if include_payments:
            payments = self.repository.list_payments_for_expense(document["_id"])
        return present_expense(document, supplier=supplier, tour=tour, payments=payments)

    def _mongo_filters(
        self,
        *,
        category: str | None = None,
        payment_status: str | None = None,
        expense_scope: str | None = None,
        supplier_id=None,
        tour_id=None,
        overdue=None,
    ) -> dict:
        extra: dict = {}
        if category:
            extra["category"] = validate_category(category)
        if payment_status:
            status = (payment_status or "").strip().upper()
            if status not in ExpenseDocument.ALLOWED_PAYMENT_STATUSES:
                raise ValidationError("Invalid payment status.")
            extra["payment_status"] = status
        if expense_scope:
            extra["expense_scope"] = validate_scope(expense_scope)
        if supplier_id:
            extra["supplier_id"] = parse_object_id(supplier_id, field="supplier_id")
        if tour_id:
            extra["tour_id"] = parse_object_id(tour_id, field="tour_id")
        return extra
