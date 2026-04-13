# tests/cloud/test_policy_engine.py — Move 5 PR-B.
# Created: 2026-04-13 — Visibility checks across FabricObject, Pocket-shaped
# dicts, and arbitrary duck-typed objects. Covers fail-open / fail-closed
# semantics for unscoped entities + filter_visible's hidden counter +
# PolicyDecision audit shape.

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ee.fabric.models import FabricObject
from ee.policy.engine import (
    PolicyDecision,
    decide,
    filter_visible,
    visible,
)


def _obj(scope: list[str] | None = None, oid: str = "obj_x") -> FabricObject:
    return FabricObject(id=oid, type_id="t", type_name="Customer", scope=scope or [])


@dataclass
class _DuckEntity:
    id: str
    scope: list[str]


# ---------------------------------------------------------------------------
# visible()
# ---------------------------------------------------------------------------


class TestVisible:
    def test_unscoped_caller_sees_everything(self) -> None:
        assert visible(_obj(["org:finance:*"]), None) is True
        assert visible(_obj(["org:finance:*"]), []) is True

    def test_unscoped_entity_visible_by_default(self) -> None:
        assert visible(_obj([]), ["org:sales:*"]) is True

    def test_unscoped_entity_blocked_when_allow_unscoped_false(self) -> None:
        assert visible(_obj([]), ["org:sales:*"], allow_unscoped=False) is False

    def test_exact_scope_match(self) -> None:
        assert visible(_obj(["org:sales:leads"]), ["org:sales:leads"]) is True

    def test_glob_match(self) -> None:
        assert visible(_obj(["org:sales:leads"]), ["org:sales:*"]) is True

    def test_no_overlap_denied(self) -> None:
        assert visible(_obj(["org:finance:*"]), ["org:sales:*"]) is False

    def test_dict_entity_supported(self) -> None:
        assert visible({"id": "x", "scope": ["org:sales:leads"]}, ["org:sales:*"]) is True

    def test_duck_typed_entity_supported(self) -> None:
        entity = _DuckEntity(id="dx", scope=["org:hr:reports"])
        # Caller's scope is broader than the entity's — wildcard grants access.
        assert visible(entity, ["org:hr:*"]) is True

    def test_string_scope_field_treated_as_single_entry(self) -> None:
        entity = _DuckEntity(id="dx", scope="org:hr:reports")  # type: ignore[arg-type]
        assert visible(entity, ["org:hr:*"]) is True

    def test_none_entity_passes_through_with_no_filter(self) -> None:
        assert visible(None, None) is True


# ---------------------------------------------------------------------------
# filter_visible()
# ---------------------------------------------------------------------------


class TestFilterVisible:
    def test_pass_through_when_caller_unscoped(self) -> None:
        items = [_obj(["org:finance:*"]), _obj([])]
        kept, hidden = filter_visible(items, None)
        assert kept == items
        assert hidden == 0

    def test_filters_disallowed_and_counts(self) -> None:
        sales = _obj(["org:sales:leads"], oid="s1")
        finance = _obj(["org:finance:reports"], oid="f1")
        unscoped = _obj([], oid="u1")

        kept, hidden = filter_visible([sales, finance, unscoped], ["org:sales:*"])
        kept_ids = [k.id for k in kept]
        assert "s1" in kept_ids
        assert "u1" in kept_ids  # unscoped passes through with default allow
        assert "f1" not in kept_ids
        assert hidden == 1

    def test_strict_mode_blocks_unscoped(self) -> None:
        sales = _obj(["org:sales:leads"], oid="s1")
        unscoped = _obj([], oid="u1")
        kept, hidden = filter_visible(
            [sales, unscoped],
            ["org:sales:*"],
            allow_unscoped=False,
        )
        assert [k.id for k in kept] == ["s1"]
        assert hidden == 1


# ---------------------------------------------------------------------------
# decide() — audit explanations
# ---------------------------------------------------------------------------


class TestDecide:
    def test_pass_through_decision_when_no_filter(self) -> None:
        d = decide(_obj(["org:sales:*"]), None)
        assert isinstance(d, PolicyDecision)
        assert d.allowed is True
        assert "no scope filter" in d.reason

    def test_unscoped_allow_decision(self) -> None:
        d = decide(_obj([]), ["org:sales:*"])
        assert d.allowed is True
        assert "allowed by default" in d.reason

    def test_unscoped_deny_decision_strict(self) -> None:
        d = decide(_obj([]), ["org:sales:*"], allow_unscoped=False)
        assert d.allowed is False

    def test_match_records_winning_scope(self) -> None:
        entity = _obj(["org:sales:leads"], oid="s1")
        d = decide(entity, ["org:other:*", "org:sales:*"])
        assert d.allowed is True
        assert d.matched_scope == "org:sales:*"

    def test_deny_records_no_match_reason(self) -> None:
        d = decide(_obj(["org:finance:*"]), ["org:sales:*"])
        assert d.allowed is False
        assert "no caller scope grants" in d.reason


# ---------------------------------------------------------------------------
# FabricObject + FabricQuery shape
# ---------------------------------------------------------------------------


class TestFabricModelScope:
    def test_fabric_object_has_default_empty_scope(self) -> None:
        obj = FabricObject(type_id="t", type_name="Customer")
        assert obj.scope == []

    def test_fabric_object_round_trips_scope(self) -> None:
        obj = FabricObject(
            type_id="t",
            type_name="Customer",
            scope=["org:sales:leads", "org:marketing:read"],
        )
        restored = FabricObject.model_validate(obj.model_dump())
        assert restored.scope == obj.scope

    def test_fabric_query_scopes_default_empty(self) -> None:
        from ee.fabric.models import FabricQuery

        q = FabricQuery()
        assert q.scopes == []

    @pytest.mark.asyncio
    async def test_fabric_store_query_filters_by_scopes(self, tmp_path) -> None:
        """Integration check — FabricStore.query() honours the new scopes filter."""
        from ee.fabric.models import FabricObject, FabricQuery
        from ee.fabric.store import FabricStore

        store = FabricStore(tmp_path / "fabric_test.db")
        otype = await store.define_type(name="Customer", properties=[])

        await store.create_object(
            FabricObject(
                type_id=otype.id,
                type_name="Customer",
                scope=["org:sales:leads"],
            ),
        )
        await store.create_object(
            FabricObject(
                type_id=otype.id,
                type_name="Customer",
                scope=["org:finance:reports"],
            ),
        )
        await store.create_object(
            FabricObject(type_id=otype.id, type_name="Customer"),  # unscoped
        )

        sales = await store.query(
            FabricQuery(type_name="Customer", scopes=["org:sales:*"]),
        )
        kept_scopes = [s for o in sales.objects for s in o.scope]
        # Sales caller sees the sales-scoped object + the unscoped one.
        assert "org:sales:leads" in kept_scopes
        assert "org:finance:reports" not in kept_scopes
        assert any(o.scope == [] for o in sales.objects)
