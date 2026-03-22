"""Tests for FlaskParser."""

import tempfile
from pathlib import Path

import pytest

from kg_mcp.parsers.flask_parser import FlaskParser

FIXTURE_WS = Path(__file__).parent / "fixtures" / "test_workspace"
PYTHON_SVC = FIXTURE_WS / "python-svc"


@pytest.fixture
def parser():
    return FlaskParser()


def test_parse_file_with_route_decorator(parser, tmp_path):
    src = tmp_path / "view.py"
    src.write_text(
        "@app.route('/test', methods=['GET'])\n"
        "def test_view():\n"
        "    return 'ok'\n"
    )
    endpoints = parser.parse_file(src)
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep.route_path == "/test"
    assert ep.http_method == "GET"
    assert ep.function_name == "test_view"


def test_parse_file_with_post_method(parser, tmp_path):
    src = tmp_path / "view.py"
    src.write_text(
        "@app.route('/submit', methods=['POST'])\n"
        "def submit():\n"
        "    pass\n"
    )
    endpoints = parser.parse_file(src)
    assert len(endpoints) == 1
    assert endpoints[0].http_method == "POST"


def test_parse_file_without_routes(parser, tmp_path):
    src = tmp_path / "plain.py"
    src.write_text("def helper():\n    return 42\n")
    endpoints = parser.parse_file(src)
    assert endpoints == []


def test_parse_file_nonexistent(parser, tmp_path):
    result = parser.parse_file(tmp_path / "missing.py")
    assert result == []


def test_resolve_namespace(parser, tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text(
        "from .controllers.user_controller import user_ns\n"
        "api.add_namespace(user_ns, path='/api/v1/user')\n"
    )
    ns_map = parser.resolve_namespace(init)
    assert "user_controller" in ns_map
    assert ns_map["user_controller"] == "/api/v1/user"


def test_resolve_namespace_missing_file(parser, tmp_path):
    result = parser.resolve_namespace(tmp_path / "__init__.py")
    assert result == {}


def test_parse_project_with_fixture(parser):
    endpoints, calls = parser.parse_project(PYTHON_SVC)
    assert len(endpoints) > 0
    urls = [ep.full_url for ep in endpoints]
    assert any("/api/v1/user/get_user" in u for u in urls)
    assert any("/api/v1/risk/get_risk" in u for u in urls)


def test_parse_project_endpoint_count(parser):
    endpoints, _ = parser.parse_project(PYTHON_SVC)
    # 2 user routes + 2 risk routes = 4 endpoints
    assert len(endpoints) >= 4


def test_parse_project_namespace_assigned(parser):
    endpoints, _ = parser.parse_project(PYTHON_SVC)
    namespaced = [ep for ep in endpoints if ep.namespace is not None]
    assert len(namespaced) > 0
