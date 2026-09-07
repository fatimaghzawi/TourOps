from __future__ import annotations

from bson import ObjectId
from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class SupplierOfferingRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        suppliers: Collection | None = None,
        packages: Collection | None = None,
        tours: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.SUPPLIER_SERVICES)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)
        self.packages = packages if packages is not None else get_collection(Collections.PACKAGES)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="supplier_service_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        return self.collection.find_one(query)

    def list_offerings(self, extra: dict | None = None) -> list[dict]:
        return list(self.collection.find(live_query(extra)).sort("name", 1))

    def find_supplier(self, supplier_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(supplier_id, field="supplier_id")})
        return self.suppliers.find_one(query)

    def find_duplicate_name(self, supplier_id, name: str, *, exclude_id=None) -> dict | None:
        query = live_query(
            {
                "supplier_id": parse_object_id(supplier_id, field="supplier_id"),
                "name_key": (name or "").strip().casefold(),
            }
        )
        if exclude_id is not None:
            query["_id"] = {"$ne": parse_object_id(exclude_id, field="supplier_service_id")}
        return self.collection.find_one(query)

    def count_package_refs(self, offering_id) -> int:
        oid = str(parse_object_id(offering_id, field="supplier_service_id"))
        count = 0
        for document in self.packages.find(live_query()):
            if self._uses_offering(document, oid):
                count += 1
        return count

    def count_tour_refs(self, offering_id) -> int:
        oid = str(parse_object_id(offering_id, field="supplier_service_id"))
        count = 0
        for document in self.tours.find(live_query()):
            if self._uses_offering(document, oid):
                count += 1
        return count

    def count_supplier_product_refs(self, supplier_id) -> int:
        oid = str(parse_object_id(supplier_id, field="supplier_id"))
        count = 0
        for document in list(self.packages.find(live_query())) + list(self.tours.find(live_query())):
            for line in document.get("services") or []:
                if not isinstance(line, dict):
                    continue
                if str(line.get("supplier_id") or "") == oid:
                    count += 1
                    break
        return count

    def _uses_offering(self, document: dict, offering_id: str) -> bool:
        for line in document.get("services") or []:
            if not isinstance(line, dict):
                continue
            if str(line.get("supplier_service_id") or "") == offering_id:
                return True
        return False
