from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    def sort(self, field: str, direction: int = 1) -> FakeCursor:
        self.documents.sort(
            key=lambda document: (document.get(field) is None, document.get(field)),
            reverse=direction < 0,
        )
        return self

    def limit(self, count: int) -> FakeCursor:
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        unique_fields: tuple[str, ...] = (),
    ) -> None:
        self.documents = deepcopy(documents or [])
        self.unique_fields = unique_fields

    @staticmethod
    def _matches_value(actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            options = expected.get("$options", "")
            for operator, operand in expected.items():
                if operator == "$options":
                    continue
                if operator == "$gte" and not (
                    actual is not None and actual >= operand
                ):
                    return False
                if operator == "$gt" and not (actual is not None and actual > operand):
                    return False
                if operator == "$lte" and not (
                    actual is not None and actual <= operand
                ):
                    return False
                if operator == "$lt" and not (actual is not None and actual < operand):
                    return False
                if operator == "$ne" and actual == operand:
                    return False
                if operator == "$in" and actual not in operand:
                    return False
                if operator == "$regex":
                    import re

                    flags = re.IGNORECASE if options == "i" else 0
                    if actual is None or re.search(operand, str(actual), flags) is None:
                        return False
            return True
        return actual == expected

    def _matches(self, document: dict[str, Any], query: dict[str, Any]) -> bool:
        for field, expected in query.items():
            if field == "$options":
                continue
            if not self._matches_value(document.get(field), expected):
                return False
        return True

    @staticmethod
    def _project(
        document: dict[str, Any],
        projection: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = deepcopy(document)
        if not projection:
            return result
        included = [field for field, value in projection.items() if value]
        if included:
            return {field: result[field] for field in included if field in result}
        for field, value in projection.items():
            if not value:
                result.pop(field, None)
        return result

    def find_one(
        self,
        query: dict[str, Any],
        projection: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        for document in self.documents:
            if self._matches(document, query):
                return self._project(document, projection)
        return None

    def find(
        self,
        query: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None,
    ) -> FakeCursor:
        query = query or {}
        return FakeCursor(
            [
                self._project(document, projection)
                for document in self.documents
                if self._matches(document, query)
            ]
        )

    def insert_one(self, document: dict[str, Any]) -> None:
        for field in self.unique_fields:
            if any(
                existing.get(field) == document.get(field)
                for existing in self.documents
            ):
                raise DuplicateKeyError(
                    "duplicate key",
                    details={"keyPattern": {field: 1}},
                )
        self.documents.append(deepcopy(document))

    def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        projection: dict[str, Any] | None = None,
        return_document: ReturnDocument = ReturnDocument.BEFORE,
    ) -> dict[str, Any] | None:
        for document in self.documents:
            if not self._matches(document, query):
                continue
            before = deepcopy(document)
            for field, value in update.get("$set", {}).items():
                document[field] = value
            for field, value in update.get("$inc", {}).items():
                document[field] = document.get(field, 0) + value
            selected = document if return_document == ReturnDocument.AFTER else before
            return self._project(selected, projection)
        return None

    def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
    ) -> None:
        for document in self.documents:
            if self._matches(document, query):
                document.update(update.get("$set", {}))
                for field, value in update.get("$inc", {}).items():
                    document[field] = document.get(field, 0) + value
                return


@pytest.fixture
def fake_collection():
    return FakeCollection


class FixedDateTime:
    fixed_now = None

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)

    @classmethod
    def fromisoformat(cls, value: str):
        from datetime import datetime

        return datetime.fromisoformat(value)


@pytest.fixture
def fixed_datetime(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    FixedDateTime.fixed_now = datetime(
        2026, 10, 11, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    return FixedDateTime
