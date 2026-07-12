from __future__ import annotations

from app.core.search.sweep import orphan_ids


def test_orphan_ids_returns_es_only():
    es = {"a", "b", "c"}
    src = {"b", "c"}
    assert orphan_ids(es, src) == {"a"}


def test_no_orphans_when_source_superset():
    assert orphan_ids({"a"}, {"a", "b"}) == set()


def test_no_orphans_when_equal():
    assert orphan_ids({"a", "b"}, {"a", "b"}) == set()
