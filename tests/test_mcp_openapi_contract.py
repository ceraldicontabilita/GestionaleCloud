"""Ensure the curated MCP catalogue cannot silently drift from FastAPI routes."""

from app.main import app
from gestionale_mcp.catalog import ACTION_OPERATIONS, READ_OPERATIONS


def test_curated_read_paths_exist_as_get_operations() -> None:
    schema = app.openapi()
    missing = [item for item in READ_OPERATIONS if "get" not in schema["paths"].get(item.path, {})]
    assert not missing, [(item.operation_id, item.path) for item in missing]


def test_confirmed_action_paths_and_methods_exist() -> None:
    schema = app.openapi()
    missing = [
        item
        for item in ACTION_OPERATIONS
        if item.method.lower() not in schema["paths"].get(item.path, {})
    ]
    assert not missing, [(item.action_id, item.method, item.path) for item in missing]


def test_catalog_has_unique_ids_and_paths() -> None:
    read_ids = [item.operation_id for item in READ_OPERATIONS]
    action_ids = [item.action_id for item in ACTION_OPERATIONS]
    assert len(read_ids) == len(set(read_ids))
    assert len(action_ids) == len(set(action_ids))
    assert set(read_ids).isdisjoint(action_ids)
