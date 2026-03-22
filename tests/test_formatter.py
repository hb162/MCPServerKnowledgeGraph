"""Tests for CompactFormatter."""

from datetime import datetime, timezone

import pytest

from kg_mcp.graph.models import (
    ApiInfo,
    BuildResult,
    CallerInfo,
    GraphStatus,
    ImpactChain,
    ImpactResult,
    ImpactStep,
    ImpactSummary,
)
from kg_mcp.output.formatter import CompactFormatter


def test_format_build_success():
    result = BuildResult(
        success=True,
        node_counts={"Project": 2, "FlaskEndpoint": 4},
        edge_counts={"defines": 10},
        cross_project_links=2,
        build_duration_seconds=1.23,
    )
    output = CompactFormatter.format_build(result)
    assert "BUILD OK" in output
    assert "1.2s" in output


def test_format_build_fail():
    result = BuildResult(
        success=False,
        build_duration_seconds=0.1,
        errors=["No projects found in workspace"],
    )
    output = CompactFormatter.format_build(result)
    assert "BUILD FAIL" in output
    assert "No projects found" in output


def test_format_build_fail_no_errors():
    result = BuildResult(success=False, build_duration_seconds=0.5)
    output = CompactFormatter.format_build(result)
    assert "BUILD FAIL" in output


def test_format_impact():
    result = ImpactResult(
        source_name="get_user",
        source_url="/api/v1/user/get_user",
        source_file="python-svc/controllers/user_controller.py",
        source_line=14,
        chains=[
            ImpactChain(steps=[
                ImpactStep(
                    name="UserTask",
                    file_path="java-test/UserTask.java",
                    line_number=5,
                    edge_type="calls_api",
                )
            ])
        ],
        summary=ImpactSummary(total_files=2, total_projects=2, max_depth=1),
    )
    output = CompactFormatter.format_impact(result)
    assert "IMPACT" in output
    assert "get_user" in output
    assert "CHAIN" in output
    assert "UserTask" in output
    assert "SUMMARY" in output
    assert "2 files" in output


def test_format_impact_includes_url():
    result = ImpactResult(
        source_name="get_user",
        source_url="/api/v1/user/get_user",
        source_file="svc/view.py",
        source_line=1,
        chains=[],
        summary=ImpactSummary(0, 0, 0),
    )
    output = CompactFormatter.format_impact(result)
    assert "/api/v1/user/get_user" in output


def test_format_not_found():
    output = CompactFormatter.format_not_found("missing_func", ["get_user", "get_risk"])
    assert "NOT FOUND" in output
    assert "missing_func" in output
    assert "SIMILAR" in output
    assert "get_user" in output


def test_format_not_found_no_suggestions():
    output = CompactFormatter.format_not_found("xyz", [])
    assert "NOT FOUND" in output
    assert "SIMILAR" not in output


def test_format_callers():
    callers = [
        CallerInfo(caller_name="UserTest", caller_type="Test", file_path="UserTest.java", line_number=6),
    ]
    output = CompactFormatter.format_callers("/api/v1/user/get_user", callers)
    assert "CALLERS" in output
    assert "/api/v1/user/get_user" in output
    assert "UserTest" in output
    assert "Test" in output


def test_format_callers_empty():
    output = CompactFormatter.format_callers("/api/v1/user/get_user", [])
    assert "NO CALLERS" in output


def test_format_api_list():
    apis = [
        ApiInfo(http_method="GET", full_url="/api/v1/user/get_user",
                function_name="get", file_path="user_controller.py", project="python-svc"),
        ApiInfo(http_method="POST", full_url="/api/v1/user/create_user",
                function_name="post", file_path="user_controller.py", project="python-svc"),
    ]
    output = CompactFormatter.format_api_list(apis)
    assert "APIS" in output
    assert "2 endpoints" in output
    assert "python-svc" in output
    assert "/api/v1/user/get_user" in output


def test_format_api_list_empty():
    output = CompactFormatter.format_api_list([])
    assert "APIS" in output
    assert "0 endpoints" in output


def test_format_status_built():
    status = GraphStatus(
        is_built=True,
        node_counts={"Project": 2, "FlaskEndpoint": 4},
        edge_counts={"defines": 10},
        last_build_time=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
        projects=["python-svc", "java-test"],
    )
    output = CompactFormatter.format_status(status)
    assert "STATUS: built" in output
    assert "python-svc" in output
    assert "java-test" in output


def test_format_status_not_built():
    status = GraphStatus(is_built=False)
    output = CompactFormatter.format_status(status)
    assert "STATUS: not_built" in output
    assert "build_graph" in output
