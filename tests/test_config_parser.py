"""Tests for ConfigParser."""

from pathlib import Path

import pytest

from kg_mcp.graph.models import ConfigReference
from kg_mcp.parsers.config_parser import ConfigParser

FIXTURE_WS = Path(__file__).parent / "fixtures" / "test_workspace"
JAVA_MAIN = FIXTURE_WS / "java-test" / "src" / "main"
CONF_FILE = JAVA_MAIN / "resources" / "application.conf"
API_CONFIG = JAVA_MAIN / "java" / "config" / "ApiConfig.java"


@pytest.fixture
def parser():
    return ConfigParser()


def test_parse_hocon(parser):
    result = parser.parse_hocon(CONF_FILE)
    assert isinstance(result, dict)
    assert len(result) > 0
    assert "user.getUser" in result
    assert result["user.getUser"] == "/api/v1/user/get_user"
    assert "risk.getRisk" in result
    assert result["risk.getRisk"] == "/api/v1/risk/get_risk"


def test_parse_hocon_all_keys(parser):
    result = parser.parse_hocon(CONF_FILE)
    assert "user.createUser" in result
    assert "risk.updateRisk" in result
    assert result["user.createUser"] == "/api/v1/user/create_user"
    assert result["risk.updateRisk"] == "/api/v1/risk/update_risk"


def test_parse_java_config(parser):
    refs = parser.parse_java_config(API_CONFIG)
    assert isinstance(refs, list)
    assert len(refs) >= 4
    keys = [r.config_key for r in refs]
    assert "user.getUser" in keys
    assert "user.createUser" in keys
    assert "risk.getRisk" in keys
    assert "risk.updateRisk" in keys


def test_parse_java_config_has_line_numbers(parser):
    refs = parser.parse_java_config(API_CONFIG)
    for ref in refs:
        assert isinstance(ref, ConfigReference)
        assert ref.line_number > 0
        assert ref.java_file != ""


def test_resolve_config_to_url(parser):
    hocon_map = {"user.getUser": "/api/v1/user/get_user"}
    refs = [ConfigReference(java_file="ApiConfig.java", config_key="user.getUser", line_number=7)]
    resolved = parser.resolve_config_to_url(refs, hocon_map)
    assert len(resolved) == 1
    assert resolved[0].resolved_url == "/api/v1/user/get_user"
    assert resolved[0].config_key == "user.getUser"


def test_resolve_config_to_url_missing_key(parser):
    hocon_map = {"other.key": "/some/url"}
    refs = [ConfigReference(java_file="ApiConfig.java", config_key="user.getUser", line_number=7)]
    resolved = parser.resolve_config_to_url(refs, hocon_map)
    assert resolved == []


def test_parse_hocon_invalid(parser, tmp_path):
    bad = tmp_path / "bad.conf"
    bad.write_text("this is { not valid hocon !!!!")
    result = parser.parse_hocon(bad)
    assert isinstance(result, dict)


def test_parse_project_configs(parser):
    hocon_map, resolved = parser.parse_project_configs(FIXTURE_WS / "java-test")
    assert len(hocon_map) >= 4
    assert len(resolved) >= 4
    urls = [r.resolved_url for r in resolved]
    assert "/api/v1/user/get_user" in urls
