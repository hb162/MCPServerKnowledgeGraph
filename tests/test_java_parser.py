"""Tests for JavaParser."""

from pathlib import Path

import pytest

from kg_mcp.graph.models import FileType
from kg_mcp.parsers.java_parser import JavaParser

FIXTURE_WS = Path(__file__).parent / "fixtures" / "test_workspace"
JAVA_SRC = FIXTURE_WS / "java-test" / "src" / "test" / "java"


@pytest.fixture
def parser():
    return JavaParser()


def test_classify_file_test(parser, tmp_path):
    f = tmp_path / "UserTest.java"
    f.touch()
    assert parser.classify_file(f) == FileType.TEST


def test_classify_file_task(parser, tmp_path):
    f = tmp_path / "UserTask.java"
    f.touch()
    assert parser.classify_file(f) == FileType.TASK


def test_classify_file_qst(parser, tmp_path):
    f = tmp_path / "UserQst.java"
    f.touch()
    assert parser.classify_file(f) == FileType.QST


def test_classify_file_entity(parser, tmp_path):
    f = tmp_path / "UserEntity.java"
    f.touch()
    assert parser.classify_file(f) == FileType.ENTITY


def test_classify_file_none(parser, tmp_path):
    f = tmp_path / "Regular.java"
    f.touch()
    assert parser.classify_file(f) is None


def test_parse_file_user_test(parser):
    node = parser.parse_file(JAVA_SRC / "UserTest.java")
    assert node is not None
    assert node.class_name == "UserTest"
    assert node.file_type == FileType.TEST
    assert len(node.methods) >= 2
    method_names = [m.name for m in node.methods]
    assert "testGetUser" in method_names
    assert "testCreateUser" in method_names


def test_parse_file_user_task(parser):
    node = parser.parse_file(JAVA_SRC / "UserTask.java")
    assert node is not None
    assert node.class_name == "UserTask"
    assert node.file_type == FileType.TASK
    assert len(node.methods) >= 2


def test_parse_file_unclassified_returns_none(parser, tmp_path):
    f = tmp_path / "Regular.java"
    f.write_text("public class Regular {}\n")
    assert parser.parse_file(f) is None


def test_parse_project_finds_all_types(parser):
    nodes = parser.parse_project(FIXTURE_WS / "java-test")
    types_found = {n.file_type for n in nodes}
    assert FileType.TEST in types_found
    assert FileType.TASK in types_found
    assert FileType.QST in types_found
    assert FileType.ENTITY in types_found


def test_parse_project_node_count(parser):
    nodes = parser.parse_project(FIXTURE_WS / "java-test")
    assert len(nodes) >= 4
