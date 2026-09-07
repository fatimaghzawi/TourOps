from apps.customers.repositories import CustomerRepository
from apps.audit.repositories import AuditLogRepository
from bson import ObjectId

from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, deletion_set, live_query, restore_set, stamp_new


def test_live_query_hides_deleted_rows():
    assert live_query() == LIVE_FILTER
    assert live_query({"email": "a@b.com"})["email"] == "a@b.com"
    assert live_query({"email": "a@b.com"})["is_deleted"]["$ne"] is True


def test_stamp_new_sets_live_flag():
    stamped = stamp_new({"name": "Ada"})
    assert stamped["is_deleted"] is False
    assert stamped["deleted_at"] is None
    assert stamped["deleted_by"] is None
    assert stamped["name"] == "Ada"


def test_deletion_set_marks_deleted():
    user_id = ObjectId()
    payload = deletion_set(user_id)
    assert payload["is_deleted"] is True
    assert payload["deleted_by"] == user_id
    assert payload["deleted_at"] is not None


def test_restore_clears_deleted_flag():
    payload = restore_set()
    assert payload["is_deleted"] is False
    assert payload["deleted_at"] is None
    assert payload["deleted_by"] is None


def test_feature_repos_use_the_shared_mixin():
    assert issubclass(CustomerRepository, SoftDeleteRepositoryMixin)
    assert not issubclass(AuditLogRepository, SoftDeleteRepositoryMixin)
