from __future__ import annotations

import copy
import re
from decimal import Decimal

from bson import ObjectId
from pymongo.errors import DuplicateKeyError


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeUpdateResult:
    def __init__(self, matched_count, modified_count):
        self.matched_count = matched_count
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, count):
        return FakeCursor(self._docs[:count])

    def sort(self, key, direction=1):
        reverse = direction == -1
        return FakeCursor(
            sorted(self._docs, key=lambda doc: (doc.get(key) is None, doc.get(key)), reverse=reverse)
        )

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self._unique_indexes: list[tuple[list, dict]] = []

    def _numeric(self, value):
        if value is None:
            return None
        try:
            return Decimal(str(getattr(value, "to_decimal", lambda: value)()))
        except Exception:
            try:
                return Decimal(str(value))
            except Exception:
                return value

    def _matches(self, document: dict, query: dict) -> bool:
        for key, expected in (query or {}).items():
            if key == "$or":
                if not any(self._matches(document, clause) for clause in expected or []):
                    return False
                continue
            if key == "$and":
                if not all(self._matches(document, clause) for clause in expected or []):
                    return False
                continue
            actual = document.get(key)
            if isinstance(expected, dict) and any(str(op).startswith("$") for op in expected):
                if "$exists" in expected:
                    present = key in document
                    if bool(expected["$exists"]) != present:
                        return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
                if "$gte" in expected:
                    left, right = self._numeric(actual), self._numeric(expected["$gte"])
                    if left is None or right is None or left < right:
                        return False
                if "$lte" in expected:
                    left, right = self._numeric(actual), self._numeric(expected["$lte"])
                    if left is None or right is None or left > right:
                        return False
                if "$gt" in expected:
                    left, right = self._numeric(actual), self._numeric(expected["$gt"])
                    if left is None or right is None or left <= right:
                        return False
                if "$lt" in expected:
                    left, right = self._numeric(actual), self._numeric(expected["$lt"])
                    if left is None or right is None or left >= right:
                        return False
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$nin" in expected and actual in expected["$nin"]:
                    return False
                if "$regex" in expected:
                    flags = re.I if "i" in str(expected.get("$options") or "") else 0
                    if not re.search(str(expected["$regex"]), str(actual or ""), flags):
                        return False
                continue
            if actual != expected:
                return False
        return True

    def find_one(self, query=None):
        for document in self.docs:
            if self._matches(document, query or {}):
                return copy.deepcopy(document)
        return None

    def find(self, query=None):
        return FakeCursor(
            [copy.deepcopy(document) for document in self.docs if self._matches(document, query or {})]
        )

    def create_index(self, keys, **options):
        if options.get("unique"):
            self._unique_indexes.append((list(keys), dict(options)))
        return "ok"

    def drop_index(self, name):
        return None

    def _index_tuple(self, document: dict, keys: list) -> tuple | None:
        values = []
        for name, _direction in keys:
            value = document.get(name)
            if value is None:
                return None
            values.append(str(value))
        return tuple(values)

    def _assert_unique(self, document: dict, *, exclude_id=None) -> None:
        for keys, options in self._unique_indexes:
            extra = {k: v for k, v in options.items() if k != "unique"}
            partial = extra.get("partialFilterExpression")
            if partial and not self._matches(document, partial):
                continue
            values = self._index_tuple(document, keys)
            if values is None:
                continue
            for other in self.docs:
                if exclude_id is not None and other.get("_id") == exclude_id:
                    continue
                if partial and not self._matches(other, partial):
                    continue
                if self._index_tuple(other, keys) == values:
                    raise DuplicateKeyError("E11000 duplicate key error")

    def insert_one(self, document):
        stored = copy.deepcopy(document)
        stored.setdefault("_id", ObjectId())
        self._assert_unique(stored)
        self.docs.append(stored)
        return FakeInsertResult(stored["_id"])

    def update_one(self, query, update):
        for document in self.docs:
            if self._matches(document, query or {}):
                trial = copy.deepcopy(document)
                self._apply_update(trial, update)
                self._assert_unique(trial, exclude_id=document.get("_id"))
                self._apply_update(document, update)
                return FakeUpdateResult(1, 1)
        return FakeUpdateResult(0, 0)

    def update_many(self, query, update):
        matched = modified = 0
        for document in self.docs:
            if self._matches(document, query or {}):
                matched += 1
                before = copy.deepcopy(document)
                trial = copy.deepcopy(document)
                self._apply_update(trial, update)
                self._assert_unique(trial, exclude_id=document.get("_id"))
                self._apply_update(document, update)
                if document != before:
                    modified += 1
        return FakeUpdateResult(matched, modified)

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        target = None
        for document in self.docs:
            if self._matches(document, query or {}):
                target = document
                break
        if target is None:
            if not upsert:
                return None
            target = copy.deepcopy(query or {})
            target.setdefault("_id", ObjectId())
            self._assert_unique(target)
            self.docs.append(target)
        trial = copy.deepcopy(target)
        self._apply_update(trial, update)
        self._assert_unique(trial, exclude_id=target.get("_id"))
        self._apply_update(target, update)
        return copy.deepcopy(target)

    def _apply_update(self, document: dict, update: dict) -> None:
        for key, amount in (update.get("$inc") or {}).items():
            current = self._numeric(document.get(key) or 0) or Decimal("0")
            delta = self._numeric(amount) or Decimal("0")
            document[key] = current + delta
        document.update(update.get("$set") or {})

    def delete_many(self, query=None):
        remaining = [document for document in self.docs if not self._matches(document, query or {})]
        deleted = len(self.docs) - len(remaining)
        self.docs = remaining
        return FakeUpdateResult(deleted, deleted)

    def count_documents(self, query=None):
        return sum(1 for document in self.docs if self._matches(document, query or {}))

    def aggregate(self, pipeline):
        docs = [copy.deepcopy(document) for document in self.docs]
        for stage in pipeline or []:
            if "$match" in stage:
                docs = [document for document in docs if self._matches(document, stage["$match"])]
            elif "$group" in stage:
                if not docs:
                    docs = []
                    continue
                group = stage["$group"]
                totals: dict = {}
                for document in docs:
                    raw = group.get("sum", {})
                    field = raw.get("$sum") if isinstance(raw, dict) else None
                    key = field[1:] if isinstance(field, str) and field.startswith("$") else None
                    amount = document.get(key, 0) if key else 0
                    try:
                        amount = Decimal(str(amount))
                    except Exception:
                        amount = Decimal("0")
                    totals["sum"] = totals.get("sum", Decimal("0")) + amount
                docs = [{"_id": group.get("_id"), "sum": totals.get("sum", Decimal("0"))}]
        return docs


class FakeMongo:
    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}

    def get_collection(self, name: str) -> FakeCollection:
        if name not in self._collections:
            collection = FakeCollection()
            from core.indexes import RECOMMENDED_INDEXES

            for collection_name, keys, unique, extra in RECOMMENDED_INDEXES:
                if collection_name != name or not unique:
                    continue
                options = {"unique": True}
                if extra:
                    options.update(extra)
                collection.create_index(keys, **options)
            self._collections[name] = collection
        return self._collections[name]
