from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from apps.packages.constants import MONEY_FIELDS
from core.constants import Collections
from core.database import get_collection
from core.money import money_dict
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class PackageRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        tours: Collection | None = None,
        suppliers: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.PACKAGES)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="package_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        document = self.collection.find_one(query)
        return money_dict(document, *MONEY_FIELDS) if document else None

    def list_packages(self, extra: dict | None = None) -> list[dict]:
        return [
            money_dict(document, *MONEY_FIELDS)
            for document in self.collection.find(live_query(extra)).sort("name", 1)
        ]

    def find_supplier(self, supplier_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(supplier_id, field="supplier_id")})
        return self.suppliers.find_one(query)

    def list_tours_for(self, package_id: str | ObjectId) -> list[dict]:
        query = live_query({"package_id": parse_object_id(package_id, field="package_id")})
        return list(self.tours.find(query).sort("start_date", 1))

    def count_tours(self, package_id: str | ObjectId) -> int:
        query = live_query({"package_id": parse_object_id(package_id, field="package_id")})
        return self.tours.count_documents(query)
