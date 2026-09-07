from __future__ import annotations

from decimal import Decimal

from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.expenses.services import ExpenseService
from apps.notifications.constants import NotificationType
from apps.notifications.services import FINANCE_NOTIFY_ROLES, safe_notify_roles
from apps.expenses.validators import parse_positive_money, parse_when
from apps.supplier_payments.constants import METHOD_LABELS
from apps.supplier_payments.repositories import SupplierPaymentRepository
from apps.supplier_payments.validators import validate_payment_method
from core.constants import Collections, DEFAULT_CURRENCY, RecordStatus
from core.exceptions import DatabaseUnavailableError, NotFoundError, ValidationError
from core.money import ZERO, to_decimal128, to_money
from core.numbering import next_number
from core.utils import parse_object_id, serialize_id, utcnow


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


def present_payment(
    document: dict,
    *,
    supplier: dict | None = None,
    expense: dict | None = None,
) -> dict:
    amount = to_money(document.get("amount"))
    supplier_name = (supplier or {}).get("name") if supplier else None
    expense_number = (expense or {}).get("expense_number") if expense else None
    return {
        "id": str(document["_id"]),
        "number": document.get("supplier_payment_number") or "",
        "supplier_payment_number": document.get("supplier_payment_number") or "",
        "supplier_id": serialize_id(document.get("supplier_id")),
        "supplier": supplier_name or "—",
        "expense_id": serialize_id(document.get("expense_id")),
        "expense": expense_number or "—",
        "amount": amount,
        "currency": document.get("currency") or DEFAULT_CURRENCY,
        "method": document.get("payment_method"),
        "payment_method": document.get("payment_method"),
        "method_label": METHOD_LABELS.get(document.get("payment_method"), document.get("payment_method") or ""),
        "date": _display_date(document.get("payment_date")),
        "payment_date": document.get("payment_date"),
        "ref": document.get("reference_number") or "",
        "reference_number": document.get("reference_number") or "",
        "notes": document.get("notes") or "",
        "recorded_by": serialize_id(document.get("recorded_by")),
        "created_at": document.get("created_at"),
    }


def serialize_payment(presented: dict) -> dict:
    payload = dict(presented)
    if isinstance(payload.get("amount"), Decimal):
        payload["amount"] = str(to_money(payload["amount"]))
    payload["payment_date"] = _iso(payload.get("payment_date"))
    payload["created_at"] = _iso(payload.get("created_at"))
    return payload


class SupplierPaymentService:
    def __init__(
        self,
        repository: SupplierPaymentRepository | None = None,
        expense_service: ExpenseService | None = None,
    ):
        self.repository = repository or SupplierPaymentRepository()
        self.expenses = expense_service or ExpenseService()

    def list_items(self, *, supplier_id=None, expense_id=None) -> list[dict]:
        extra = {}
        if supplier_id:
            extra["supplier_id"] = parse_object_id(supplier_id, field="supplier_id")
        if expense_id:
            extra["expense_id"] = parse_object_id(expense_id, field="expense_id")
        return self.repository.list_payments(extra or None)

    def list_presented(self, **filters) -> list[dict]:
        return [self._present(doc) for doc in self.list_items(**filters)]

    def get(self, payment_id) -> dict:
        try:
            document = self.repository.find_by_id(payment_id)
        except ValidationError as extra:
            raise NotFoundError("Supplier payment not found.") from extra
        if not document:
            raise NotFoundError("Supplier payment not found.")
        return document

    def get_presented(self, payment_id) -> dict:
        return self._present(self.get(payment_id))

    def create(
        self,
        *,
        actor_id,
        expense_id,
        amount,
        payment_method: str,
        payment_date=None,
        reference_number: str | None = None,
        notes: str | None = None,
        currency: str | None = None,
        supplier_id=None,
    ) -> dict:
        if not expense_id:
            raise ValidationError("Expense is required.")
        expense = self.expenses.get(expense_id)
        if not expense.get("supplier_id"):
            raise ValidationError("This expense has no supplier to pay.")
        expense_supplier = expense["supplier_id"]
        if supplier_id:
            requested = parse_object_id(supplier_id, field="supplier_id")
            if requested != expense_supplier:
                raise ValidationError("Expense does not belong to this supplier.")
        supplier = self.repository.find_supplier(expense_supplier)
        if not supplier:
            raise ValidationError("Supplier not found.")
        if supplier.get("status") == RecordStatus.INACTIVE.value:
            raise ValidationError("Cannot pay an inactive supplier.")

        remaining = to_money(expense.get("remaining_amount"))
        if remaining <= ZERO:
            raise ValidationError("This expense is already paid in full.")
        money = parse_positive_money(amount, field="amount")
        if money > remaining:
            raise ValidationError(f"Amount cannot exceed the remaining balance of {remaining}.")

        reserved = self.expenses.repository.try_consume_remaining(expense["_id"], money)
        if not reserved:
            raise ValidationError(f"Amount cannot exceed the remaining balance of {remaining}.")

        method = validate_payment_method(payment_method)
        when = parse_when(payment_date, field="payment_date") if payment_date not in (None, "") else utcnow()
        expense_currency = (expense.get("currency") or DEFAULT_CURRENCY).upper()
        currency = (currency or expense_currency).strip().upper() or expense_currency
        if len(currency) != 3:
            raise ValidationError("Currency must be a 3-letter code.")
        if currency != expense_currency:
            raise ValidationError("Payment currency must match the expense currency.")

        now = utcnow()
        document = {
            "supplier_payment_number": next_number(Collections.SUPPLIER_PAYMENTS),
            "supplier_id": expense_supplier,
            "expense_id": expense["_id"],
            "amount": to_decimal128(money),
            "currency": currency,
            "payment_method": method,
            "payment_date": when,
            "recorded_by": parse_object_id(actor_id, field="recorded_by"),
            "created_at": now,
            "reference_number": (reference_number or "").strip() or None,
            "notes": (notes or "").strip() or None,
        }
        try:
            result = self.repository.insert(document)
        except DuplicateKeyError as extra:
            self.expenses.sync_paid_amount(
                expense["_id"],
                self.repository.sum_for_expense(expense["_id"]),
            )
            raise ValidationError("A supplier payment with this number already exists.") from extra
        except PyMongoError as extra:
            self.expenses.sync_paid_amount(
                expense["_id"],
                self.repository.sum_for_expense(expense["_id"]),
            )
            raise DatabaseUnavailableError("Could not save the supplier payment.") from extra
        document["_id"] = result.inserted_id
        self._sync_expense(expense["_id"])
        saved = self.get(document["_id"])
        number = saved.get("supplier_payment_number") or ""
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.CREATED.value,
            entity_type="supplier_payments",
            entity_id=saved["_id"],
            description=f"Recorded supplier payment {number}.",
            after={"supplier_payment_number": number, "amount": str(to_money(saved.get("amount")))},
        )
        safe_notify_roles(
            FINANCE_NOTIFY_ROLES,
            type=NotificationType.SUPPLIER.value,
            title=f"Supplier payment {number}",
            message=f"A supplier payment of {to_money(saved.get('amount'))} was recorded.",
            related_entity_type="supplier_payments",
            related_entity_id=saved["_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def void(self, payment_id, *, actor_id) -> None:
        document = self.get(payment_id)
        try:
            result = self.repository.soft_delete(document["_id"], actor_id)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not void the supplier payment.") from extra
        if result.matched_count != 1:
            raise NotFoundError("Supplier payment not found.")
        self._sync_expense(document["expense_id"])
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.VOIDED.value,
            entity_type="supplier_payments",
            entity_id=document["_id"],
            description=f"Voided supplier payment {document.get('supplier_payment_number') or ''}.",
        )

    def list_for_supplier(self, supplier_id) -> list[dict]:
        supplier = self.repository.find_supplier(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found.")
        return self.list_presented(supplier_id=supplier["_id"])

    def open_expense_choices(self, *, supplier_id=None, include_id=None) -> list[tuple[str, str]]:
        filters = {}
        if supplier_id:
            filters["supplier_id"] = supplier_id
        choices = []
        seen = set()
        for row in self.expenses.list_presented(**filters):
            if not row.get("supplier_id") or not row["has_remaining"]:
                continue
            label = f"{row['number']} · {row['supplier']} · {row['remaining']} remaining"
            choices.append((row["id"], label))
            seen.add(row["id"])
        if include_id and str(include_id) not in seen:
            try:
                row = self.expenses.get_presented(include_id)
            except NotFoundError:
                row = None
            if row and row.get("supplier_id") and row["has_remaining"]:
                choices.append((row["id"], f"{row['number']} · {row['supplier']} · {row['remaining']} remaining"))
        return choices

    def _sync_expense(self, expense_id) -> None:
        total = self.repository.sum_for_expense(expense_id)
        self.expenses.sync_paid_amount(expense_id, total)

    def _present(self, document: dict) -> dict:
        supplier = None
        expense = None
        if document.get("supplier_id"):
            supplier = self.repository.find_supplier(document["supplier_id"])
        if document.get("expense_id"):
            expense = self.repository.find_expense(document["expense_id"])
        return present_payment(document, supplier=supplier, expense=expense)
