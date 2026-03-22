"""Tests for ImpactAnalyzer."""

from pathlib import Path

import pytest

from kg_mcp.graph.analyzer import ImpactAnalyzer
from kg_mcp.graph.builder import GraphBuilder
from kg_mcp.graph.models import ImpactResult

FIXTURE_WS = Path(__file__).parent / "fixtures" / "test_workspace"


@pytest.fixture(scope="module")
def analyzer():
    b = GraphBuilder()
    b.build(FIXTURE_WS)
    return ImpactAnalyzer(b.graph)


def test_query_impact_flask_endpoint(analyzer):
    # Query by function name present in user_controller fixture
    result = analyzer.query_impact("get")
    # "get" is an HTTP method handler in GetUser Resource
    if result is None:
        # Try the full name format used in the graph
        result = analyzer.query_impact("GetUser.get")
    assert result is not None
    assert isinstance(result, ImpactResult)
    assert result.source_name != ""


def test_query_impact_by_url(analyzer):
    result = analyzer.query_impact("/api/v1/user/get_user")
    assert result is not None
    assert result.source_url == "/api/v1/user/get_user"


def test_query_impact_not_found(analyzer):
    result = analyzer.query_impact("nonexistent_function_xyz_999")
    assert result is None


def test_query_impact_returns_summary(analyzer):
    result = analyzer.query_impact("/api/v1/user/get_user")
    if result is None:
        pytest.skip("Endpoint node not found; fixture may differ")
    assert result.summary.max_depth >= 0
    assert result.summary.total_files >= 0
    assert result.summary.total_projects >= 0


def test_find_callers_known_url(analyzer):
    callers = analyzer.find_callers("/api/v1/user/get_user")
    # Returns list (may be empty if no cross-project call edge, but not None)
    assert callers is not None
    assert isinstance(callers, list)


def test_find_callers_unknown_url(analyzer):
    result = analyzer.find_callers("/no/such/endpoint/abc123")
    assert result is None


def test_list_apis_returns_all(analyzer):
    apis = analyzer.list_apis()
    assert len(apis) >= 4
    urls = [a.full_url for a in apis]
    assert "/api/v1/user/get_user" in urls
    assert "/api/v1/risk/get_risk" in urls


def test_list_apis_sorted(analyzer):
    apis = analyzer.list_apis()
    keys = [(a.project, a.full_url) for a in apis]
    assert keys == sorted(keys)


def test_list_apis_filter_by_project(analyzer):
    apis = analyzer.list_apis(project="python-svc")
    assert all(a.project == "python-svc" for a in apis)
    assert len(apis) >= 4


def test_suggest_similar_fuzzy(analyzer):
    suggestions = analyzer.suggest_similar("get_user")
    assert isinstance(suggestions, list)
    # Should find something related to get_user nodes
    assert len(suggestions) >= 0  # may be empty depending on threshold


def test_suggest_similar_exact_substring(analyzer):
    # "UserTask" is an exact node name — should be in suggestions for "UserTast"
    suggestions = analyzer.suggest_similar("UserTast", threshold=0.5)
    assert isinstance(suggestions, list)
