"""Tests for GraphBuilder."""

import tempfile
from pathlib import Path

import pytest

from kg_mcp.graph.builder import GraphBuilder
from kg_mcp.graph.models import NodeType

FIXTURE_WS = Path(__file__).parent / "fixtures" / "test_workspace"


@pytest.fixture
def builder():
    return GraphBuilder()


@pytest.fixture
def built_builder():
    b = GraphBuilder()
    b.build(FIXTURE_WS)
    return b


def test_build_from_fixture_workspace(builder):
    result = builder.build(FIXTURE_WS)
    assert result.success is True
    assert len(builder.graph.nodes) > 0
    assert len(builder.graph.edges) > 0


def test_build_node_types_present(built_builder):
    types = {d.get("type") for _, d in built_builder.graph.nodes(data=True)}
    assert NodeType.PROJECT.value in types
    assert NodeType.FLASK_ENDPOINT.value in types
    assert NodeType.JAVA_TEST.value in types
    assert NodeType.JAVA_TASK.value in types


def test_build_result_counts(built_builder):
    result = built_builder.build(FIXTURE_WS)
    assert NodeType.FLASK_ENDPOINT.value in result.node_counts
    assert result.node_counts[NodeType.FLASK_ENDPOINT.value] >= 4


def test_url_matching(builder):
    result = builder.build(FIXTURE_WS)
    # Flask endpoints from python-svc match URLs in application.conf via ApiConfig.java
    assert result.cross_project_links >= 1


def test_build_creates_project_nodes(built_builder):
    project_nodes = [
        nid for nid, d in built_builder.graph.nodes(data=True)
        if d.get("type") == NodeType.PROJECT.value
    ]
    names = [built_builder.graph.nodes[nid]["name"] for nid in project_nodes]
    assert "python-svc" in names
    assert "java-test" in names


def test_save_and_load(tmp_path):
    b1 = GraphBuilder()
    b1.build(FIXTURE_WS)
    save_path = tmp_path / "graph.pkl"
    b1.save(save_path)

    b2 = GraphBuilder()
    ok = b2.load(save_path)
    assert ok is True
    assert len(b2.graph.nodes) == len(b1.graph.nodes)
    assert len(b2.graph.edges) == len(b1.graph.edges)


def test_load_nonexistent_returns_false(builder, tmp_path):
    assert builder.load(tmp_path / "missing.pkl") is False


def test_build_empty_workspace(builder, tmp_path):
    result = builder.build(tmp_path)
    assert result.success is False
    assert len(result.errors) > 0
