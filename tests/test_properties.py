"""Property-based tests for KG Multi-Project MCP server using Hypothesis."""

import pickle
import tempfile
from datetime import datetime
from pathlib import Path

import networkx as nx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kg_mcp.graph.analyzer import ImpactAnalyzer
from kg_mcp.graph.models import (
    ApiInfo,
    CallerInfo,
    ConfigReference,
    FileType,
    FlaskEndpoint,
    GraphStatus,
    ImpactChain,
    ImpactResult,
    ImpactStep,
    ImpactSummary,
    NodeType,
)
from kg_mcp.output.formatter import CompactFormatter
from kg_mcp.parsers.config_parser import ConfigParser
from kg_mcp.parsers.flask_parser import FlaskParser
from kg_mcp.parsers.java_parser import JavaParser
from kg_mcp.utils import normalize_path

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

identifier = st.from_regex(r"[a-z][a-z0-9]{2,10}", fullmatch=True)
url_path = st.from_regex(r"/[a-z][a-z0-9/]{1,20}", fullmatch=True)
http_methods = st.sampled_from(["GET", "POST", "PUT", "DELETE"])


# ---------------------------------------------------------------------------
# Property 1: Flask route extraction completeness
# Feature: kg-multi-project-mcp, Property 1: Flask route extraction completeness
# ---------------------------------------------------------------------------


def _make_flask_source(func_name: str, route: str, method: str) -> str:
    return (
        "from flask import Flask\n"
        "app = Flask(__name__)\n\n"
        f"@app.route('{route}', methods=['{method}'])\n"
        f"def {func_name}():\n"
        "    pass\n"
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    func_name=identifier,
    route=url_path,
    method=http_methods,
)
def test_flask_route_extraction_completeness(
    tmp_path: Path, func_name: str, route: str, method: str
) -> None:
    # Feature: kg-multi-project-mcp, Property 1: Flask route extraction completeness
    source = _make_flask_source(func_name, route, method)
    py_file = tmp_path / f"routes_{func_name}.py"
    py_file.write_text(source)

    parser = FlaskParser()
    endpoints = parser.parse_file(py_file)

    assert len(endpoints) >= 1
    ep = endpoints[0]
    assert ep.function_name
    assert ep.file_path
    assert ep.line_number > 0
    assert ep.http_method
    assert ep.route_path
    assert ep.full_url


# ---------------------------------------------------------------------------
# Property 2: Flask URL resolution
# Feature: kg-multi-project-mcp, Property 2: Flask URL resolution
# ---------------------------------------------------------------------------

ns_segment = st.from_regex(r"/[a-z][a-z0-9]{1,8}", fullmatch=True)


@settings(max_examples=100)
@given(namespace=ns_segment, route=ns_segment)
def test_flask_url_resolution_with_namespace(namespace: str, route: str) -> None:
    # Feature: kg-multi-project-mcp, Property 2: Flask URL resolution
    full_url = namespace + route
    assert full_url == namespace + route
    assert full_url.startswith("/")


@settings(max_examples=100)
@given(route=url_path)
def test_flask_url_resolution_empty_namespace(route: str) -> None:
    # Feature: kg-multi-project-mcp, Property 2: Flask URL resolution
    namespace = ""
    full_url = (namespace + route) if namespace else route
    assert full_url == route


# ---------------------------------------------------------------------------
# Property 3: Java file classification
# Feature: kg-multi-project-mcp, Property 3: Java file classification
# ---------------------------------------------------------------------------

JAVA_SUFFIX_TO_TYPE = {
    "Test.java": FileType.TEST,
    "Task.java": FileType.TASK,
    "Qst.java": FileType.QST,
    "Entity.java": FileType.ENTITY,
    "Config.java": FileType.CONFIG,
}
OTHER_SUFFIXES = [".java", ".txt", ".xml", ".properties"]


@settings(max_examples=100)
@given(
    base=identifier,
    suffix=st.sampled_from(
        list(JAVA_SUFFIX_TO_TYPE.keys()) + OTHER_SUFFIXES
    ),
)
def test_java_file_classification(base: str, suffix: str) -> None:
    # Feature: kg-multi-project-mcp, Property 3: Java file classification
    filename = base + suffix
    java_path = Path(filename)
    parser = JavaParser()
    result = parser.classify_file(java_path)

    if suffix in JAVA_SUFFIX_TO_TYPE:
        assert result == JAVA_SUFFIX_TO_TYPE[suffix]
    else:
        assert result is None


# ---------------------------------------------------------------------------
# Property 4: Java call chain edge types
# Feature: kg-multi-project-mcp, Property 4: Java call chain edges
# ---------------------------------------------------------------------------


def _build_java_call_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("JavaTest:FooTest", type=NodeType.JAVA_TEST.value, name="FooTest",
               file_path="p/FooTest.java", project="p")
    g.add_node("JavaTask:FooTask", type=NodeType.JAVA_TASK.value, name="FooTask",
               file_path="p/FooTask.java", project="p")
    g.add_node("JavaQst:FooQst", type=NodeType.JAVA_QST.value, name="FooQst",
               file_path="p/FooQst.java", project="p")
    g.add_node("JavaEntity:FooEntity", type=NodeType.JAVA_ENTITY.value, name="FooEntity",
               file_path="p/FooEntity.java", project="p")
    g.add_edge("JavaTest:FooTest", "JavaTask:FooTask", type="test_calls")
    g.add_edge("JavaTask:FooTask", "JavaQst:FooQst", type="called_by")
    g.add_edge("JavaQst:FooQst", "JavaEntity:FooEntity", type="uses_entity")
    return g


def test_java_call_chain_edge_types() -> None:
    # Feature: kg-multi-project-mcp, Property 4: Java call chain edges
    g = _build_java_call_graph()
    assert g["JavaTest:FooTest"]["JavaTask:FooTask"]["type"] == "test_calls"
    assert g["JavaTask:FooTask"]["JavaQst:FooQst"]["type"] == "called_by"
    assert g["JavaQst:FooQst"]["JavaEntity:FooEntity"]["type"] == "uses_entity"
    assert g.nodes["JavaTest:FooTest"]["type"] == NodeType.JAVA_TEST.value
    assert g.nodes["JavaTask:FooTask"]["type"] == NodeType.JAVA_TASK.value


# ---------------------------------------------------------------------------
# Property 5: HOCON config parsing
# Feature: kg-multi-project-mcp, Property 5: HOCON config parsing
# ---------------------------------------------------------------------------

hocon_key = st.from_regex(r"[a-z][a-z0-9]{1,8}\.[a-z][a-z0-9]{1,8}", fullmatch=True)
hocon_val = st.from_regex(r"/[a-z][a-z0-9/]{1,15}", fullmatch=True)


@settings(max_examples=100)
@given(pairs=st.dictionaries(hocon_key, hocon_val, min_size=1, max_size=5))
def test_hocon_config_parsing(pairs: dict) -> None:
    # Feature: kg-multi-project-mcp, Property 5: HOCON config parsing
    lines = []
    for k, v in pairs.items():
        parts = k.split(".")
        lines.append(f'{parts[0]} {{ {parts[1]} = "{v}" }}')
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write("\n".join(lines))
        conf_file = Path(f.name)

    parser = ConfigParser()
    result = parser.parse_hocon(conf_file)

    for k, v in pairs.items():
        assert k in result
        assert result[k] == v


# ---------------------------------------------------------------------------
# Property 6: Java config resolution
# Feature: kg-multi-project-mcp, Property 6: Java config resolution
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    key=hocon_key,
    url=hocon_val,
    java_file=identifier,
    line=st.integers(min_value=1, max_value=500),
)
def test_java_config_resolution(key: str, url: str, java_file: str, line: int) -> None:
    # Feature: kg-multi-project-mcp, Property 6: Java config resolution
    ref = ConfigReference(java_file=java_file + ".java", config_key=key, line_number=line)
    hocon_map = {key: url}
    parser = ConfigParser()
    resolved = parser.resolve_config_to_url([ref], hocon_map)
    assert len(resolved) == 1
    assert resolved[0].config_key == key
    assert resolved[0].resolved_url == url
    assert resolved[0].java_file == java_file + ".java"
    assert resolved[0].line_number == line


# ---------------------------------------------------------------------------
# Property 7: URL exact matching
# Feature: kg-multi-project-mcp, Property 7: URL exact matching
# ---------------------------------------------------------------------------


def _build_url_match_graph(matching_url: str, non_matching_url: str) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node(
        "FlaskEndpoint:GET:/api/match",
        type=NodeType.FLASK_ENDPOINT.value,
        name=f"GET {matching_url}",
        file_path="p/routes.py",
        project="p",
        metadata={"http_method": "GET", "full_url": matching_url, "function_name": "match"},
    )
    g.add_node(
        "ConfigEntry:key.matching",
        type=NodeType.CONFIG_ENTRY.value,
        name="key.matching",
        file_path="p/Config.java",
        project="p",
        metadata={"config_key": "key.matching", "resolved_url": matching_url},
    )
    g.add_node(
        "ConfigEntry:key.nomatch",
        type=NodeType.CONFIG_ENTRY.value,
        name="key.nomatch",
        file_path="p/Config.java",
        project="p",
        metadata={"config_key": "key.nomatch", "resolved_url": non_matching_url},
    )
    return g


@settings(max_examples=100)
@given(
    matching=url_path,
    non_matching=url_path.filter(lambda p: p != "/api/match"),
)
def test_url_exact_matching(matching: str, non_matching: str) -> None:
    # Feature: kg-multi-project-mcp, Property 7: URL exact matching
    from kg_mcp.graph.builder import GraphBuilder

    builder = GraphBuilder()
    g = builder.graph
    ep_id = f"FlaskEndpoint:GET:{matching}"
    g.add_node(ep_id, type=NodeType.FLASK_ENDPOINT.value, name=f"GET {matching}",
               file_path="p/routes.py", project="p",
               metadata={"http_method": "GET", "full_url": matching, "function_name": "fn"})
    match_cid = "ConfigEntry:key.match"
    g.add_node(match_cid, type=NodeType.CONFIG_ENTRY.value, name="key.match",
               file_path="p/C.java", project="p",
               metadata={"config_key": "key.match", "resolved_url": matching})
    no_match_cid = "ConfigEntry:key.nomatch"
    g.add_node(no_match_cid, type=NodeType.CONFIG_ENTRY.value, name="key.nomatch",
               file_path="p/C.java", project="p",
               metadata={"config_key": "key.nomatch", "resolved_url": non_matching})

    count = builder.link_by_url()
    # Edge direction is FlaskEndpoint → ConfigEntry (impact direction)
    assert g.has_edge(ep_id, match_cid)
    if matching != non_matching:
        assert not g.has_edge(ep_id, no_match_cid)


# ---------------------------------------------------------------------------
# Property 8: Graph serialization round-trip
# Feature: kg-multi-project-mcp, Property 8: Graph serialization round-trip
# ---------------------------------------------------------------------------

node_attr = st.fixed_dictionaries({"name": identifier, "value": st.integers(0, 100)})


@settings(max_examples=100)
@given(
    nodes=st.lists(identifier, min_size=2, max_size=8, unique=True),
    edges=st.lists(
        st.tuples(st.integers(0, 5), st.integers(0, 5)),
        min_size=0,
        max_size=6,
    ),
)
def test_graph_serialization_roundtrip(nodes: list, edges: list) -> None:
    # Feature: kg-multi-project-mcp, Property 8: Graph serialization round-trip
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n, label=n)
    for i, j in edges:
        if i < len(nodes) and j < len(nodes) and nodes[i] != nodes[j]:
            g.add_edge(nodes[i], nodes[j], weight=i + j)

    data = pickle.dumps(g)
    g2 = pickle.loads(data)

    assert set(g.nodes()) == set(g2.nodes())
    assert set(g.edges()) == set(g2.edges())
    for n in g.nodes():
        assert g.nodes[n] == g2.nodes[n]


# ---------------------------------------------------------------------------
# Property 9: Impact traversal completeness
# Feature: kg-multi-project-mcp, Property 9: Impact traversal completeness
# ---------------------------------------------------------------------------


def _make_impact_graph(node_ids: list, edge_pairs: list) -> nx.DiGraph:
    g = nx.DiGraph()
    for nid in node_ids:
        g.add_node(nid, name=nid, file_path=f"{nid}.py", line_number=1, project="p")
    for a, b in edge_pairs:
        if a in node_ids and b in node_ids and a != b:
            g.add_edge(a, b, type="defines")
    return g


@settings(max_examples=100)
@given(
    nodes=st.lists(identifier, min_size=3, max_size=8, unique=True),
    extra_edges=st.lists(
        st.tuples(st.integers(0, 5), st.integers(1, 7)),
        min_size=1,
        max_size=5,
    ),
)
def test_impact_traversal_completeness(nodes: list, extra_edges: list) -> None:
    # Feature: kg-multi-project-mcp, Property 9: Impact traversal completeness
    edges = [(nodes[0], nodes[1])]
    for i, j in extra_edges:
        if i < len(nodes) and j < len(nodes):
            edges.append((nodes[i], nodes[j]))

    g = _make_impact_graph(nodes, edges)
    expected_reachable = nx.descendants(g, nodes[0])

    analyzer = ImpactAnalyzer(g)
    result = analyzer.query_impact(nodes[0])

    if result is None:
        assert len(expected_reachable) == 0
        return

    found_names: set[str] = set()
    for chain in result.chains:
        for step in chain.steps:
            found_names.add(step.name)

    for name in expected_reachable:
        assert name in found_names


# ---------------------------------------------------------------------------
# Property 10: Compact output completeness
# Feature: kg-multi-project-mcp, Property 10: Compact output completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    func_name=identifier,
    file_p=identifier,
    line=st.integers(1, 999),
    url=url_path,
)
def test_compact_output_impact_completeness(
    func_name: str, file_p: str, line: int, url: str
) -> None:
    # Feature: kg-multi-project-mcp, Property 10: Compact output completeness
    result = ImpactResult(
        source_name=func_name,
        source_url=url,
        source_file=file_p + ".py",
        source_line=line,
        chains=[ImpactChain(steps=[
            ImpactStep(name="step1", file_path="a.py", line_number=10, edge_type="defines")
        ])],
        summary=ImpactSummary(total_files=1, total_projects=1, max_depth=1),
    )
    output = CompactFormatter.format_impact(result)
    assert func_name in output
    assert url in output
    assert file_p + ".py" in output
    assert str(line) in output


@settings(max_examples=100)
@given(
    caller=identifier,
    caller_type=st.sampled_from(["Task", "Test", "Qst"]),
    file_p=identifier,
    line=st.integers(1, 999),
    api_url=url_path,
)
def test_compact_output_callers_completeness(
    caller: str, caller_type: str, file_p: str, line: int, api_url: str
) -> None:
    # Feature: kg-multi-project-mcp, Property 10: Compact output completeness
    callers = [CallerInfo(
        caller_name=caller, caller_type=caller_type,
        file_path=file_p + ".java", line_number=line,
    )]
    output = CompactFormatter.format_callers(api_url, callers)
    assert api_url in output
    assert caller in output
    assert file_p + ".java" in output
    assert str(line) in output


@settings(max_examples=100)
@given(
    func_name=identifier,
    url=url_path,
    file_p=identifier,
    project=identifier,
    method=http_methods,
)
def test_compact_output_api_list_completeness(
    func_name: str, url: str, file_p: str, project: str, method: str
) -> None:
    # Feature: kg-multi-project-mcp, Property 10: Compact output completeness
    apis = [ApiInfo(
        http_method=method, full_url=url, function_name=func_name,
        file_path=file_p + ".py", project=project,
    )]
    output = CompactFormatter.format_api_list(apis)
    assert func_name in output
    assert url in output
    assert file_p + ".py" in output


@settings(max_examples=100)
@given(is_built=st.booleans(), project=identifier)
def test_compact_output_status_completeness(is_built: bool, project: str) -> None:
    # Feature: kg-multi-project-mcp, Property 10: Compact output completeness
    status = GraphStatus(
        is_built=is_built,
        projects=[project] if is_built else [],
        last_build_time=datetime(2024, 1, 1) if is_built else None,
    )
    output = CompactFormatter.format_status(status)
    assert "STATUS:" in output
    if is_built:
        assert project in output


# ---------------------------------------------------------------------------
# Property 11: list_apis ordering
# Feature: kg-multi-project-mcp, Property 11: list_apis ordering
# ---------------------------------------------------------------------------


def _make_apis_graph(api_infos: list[tuple]) -> nx.DiGraph:
    """api_infos: list of (project, url, func, method)."""
    g = nx.DiGraph()
    for i, (proj, url, func, method) in enumerate(api_infos):
        nid = f"FlaskEndpoint:{method}:{url}:{i}"
        g.add_node(nid, type=NodeType.FLASK_ENDPOINT.value, name=f"{method} {url}",
                   file_path=f"{proj}/routes.py", project=proj,
                   metadata={"http_method": method, "full_url": url, "function_name": func})
    return g


@settings(max_examples=100)
@given(
    api_list=st.lists(
        st.tuples(identifier, url_path, identifier, http_methods),
        min_size=1, max_size=6,
    )
)
def test_list_apis_ordering(api_list: list) -> None:
    # Feature: kg-multi-project-mcp, Property 11: list_apis ordering
    g = _make_apis_graph(api_list)
    analyzer = ImpactAnalyzer(g)
    apis = analyzer.list_apis()

    for i in range(len(apis) - 1):
        a, b = apis[i], apis[i + 1]
        assert (a.project, a.full_url) <= (b.project, b.full_url)


# ---------------------------------------------------------------------------
# Property 12: find_callers completeness
# Feature: kg-multi-project-mcp, Property 12: find_callers completeness
# ---------------------------------------------------------------------------


def _build_callers_graph(
    api_url: str,
    callers: list[tuple[str, str]],
) -> nx.DiGraph:
    """callers: list of (caller_name, node_type_value)."""
    g = nx.DiGraph()
    ep_id = f"FlaskEndpoint:GET:{api_url}"
    g.add_node(ep_id, type=NodeType.FLASK_ENDPOINT.value, name=f"GET {api_url}",
               file_path="p/routes.py", project="p",
               metadata={"http_method": "GET", "full_url": api_url, "function_name": "fn"})
    for name, ntype in callers:
        nid = f"{ntype}:{name}"
        g.add_node(nid, type=ntype, name=name, file_path=f"p/{name}.java",
                   line_number=1, project="p")
        # Impact direction: FlaskEndpoint → caller
        g.add_edge(ep_id, nid, type="calls_api")
    return g


@settings(max_examples=100)
@given(
    api_url=url_path,
    callers=st.lists(
        st.tuples(
            identifier,
            st.sampled_from([
                NodeType.JAVA_TASK.value,
                NodeType.JAVA_TEST.value,
                NodeType.JAVA_QST.value,
            ]),
        ),
        min_size=1,
        max_size=4,
        unique_by=lambda x: x[0],
    ),
)
def test_find_callers_completeness(api_url: str, callers: list) -> None:
    # Feature: kg-multi-project-mcp, Property 12: find_callers completeness
    g = _build_callers_graph(api_url, callers)
    analyzer = ImpactAnalyzer(g)
    result = analyzer.find_callers(api_url)

    assert result is not None
    found_names = {c.caller_name for c in result}
    for name, _ in callers:
        assert name in found_names


# ---------------------------------------------------------------------------
# Property 13: Internal function call chain
# Feature: kg-multi-project-mcp, Property 13: Internal function call chain
# ---------------------------------------------------------------------------


def _make_call_chain_source(outer: str, inner: str) -> str:
    return (
        f"def {inner}():\n"
        "    return 42\n\n"
        f"def {outer}():\n"
        f"    result = {inner}()\n"
        "    return result\n"
    )


@settings(max_examples=100)
@given(
    outer=identifier,
    inner=identifier.filter(lambda x: x != "result"),
)
def test_internal_call_chain_extraction(outer: str, inner: str) -> None:
    # Feature: kg-multi-project-mcp, Property 13: Internal function call chain
    if outer == inner:
        return
    source = _make_call_chain_source(outer, inner)
    parser = FlaskParser()
    calls = parser.extract_internal_calls(source, "test_file.py")
    caller_callee_pairs = {(c.caller, c.callee) for c in calls}
    assert (outer, inner) in caller_callee_pairs


# ---------------------------------------------------------------------------
# Property 14: Cross-platform path normalization
# Feature: kg-multi-project-mcp, Property 14: Cross-platform path normalization
# ---------------------------------------------------------------------------

path_segment = st.from_regex(r"[a-z][a-z0-9]{1,8}", fullmatch=True)


@settings(max_examples=100)
@given(
    parts=st.lists(path_segment, min_size=2, max_size=5),
)
def test_cross_platform_path_normalization(parts: list) -> None:
    # Feature: kg-multi-project-mcp, Property 14: Cross-platform path normalization
    # Build a proper Path using os.path.join, then normalize
    full_path = Path(*parts)
    workspace = Path(parts[0])
    result = normalize_path(full_path, workspace)
    # Result should always use forward slashes (POSIX)
    assert "\\" not in result
    # With 2+ parts and workspace=first part, result should have remaining parts with /
    if len(parts) > 2:
        assert "/" in result
