"""Build and manage the Knowledge Graph from parser outputs."""

import logging
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from kg_mcp.graph.models import (
    BuildResult,
    EdgeType,
    FlaskEndpoint,
    FunctionCall,
    GraphState,
    JavaNode,
    NodeType,
    ResolvedConfig,
)
from kg_mcp.parsers.config_parser import ConfigParser
from kg_mcp.parsers.flask_parser import FlaskParser
from kg_mcp.parsers.java_parser import JavaParser
from kg_mcp.utils import normalize_path

logger = logging.getLogger(__name__)

GRAPH_VERSION = "1.0.0"


class GraphBuilder:
    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._flask_parser = FlaskParser()
        self._java_parser = JavaParser()
        self._config_parser = ConfigParser()

    # ------------------------------------------------------------------
    # Build orchestration
    # ------------------------------------------------------------------

    def build(self, workspace_path: Path) -> BuildResult:
        """Scan all projects in workspace and build the Knowledge Graph."""
        start = time.monotonic()
        self.graph.clear()
        errors: list[str] = []
        warnings: list[str] = []
        projects: list[str] = []

        subdirs = sorted(
            p for p in workspace_path.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        if not subdirs:
            return BuildResult(
                success=False,
                build_duration_seconds=time.monotonic() - start,
                errors=["No projects found in workspace"],
            )

        for project_dir in subdirs:
            project_name = project_dir.name
            projects.append(project_name)
            self._add_project_node(project_name)

            # Parse Flask endpoints
            try:
                endpoints, func_calls = self._flask_parser.parse_project(project_dir)
                self.add_flask_endpoints(endpoints, project_name, workspace_path)
                self._add_function_calls(func_calls, project_name, workspace_path)
            except Exception as e:
                errors.append(f"[E] {project_name}: Flask parse error: {e}")

            # Parse Java files
            try:
                java_nodes = self._java_parser.parse_project(project_dir)
                self.add_java_nodes(java_nodes, project_name, workspace_path)
            except Exception as e:
                errors.append(f"[E] {project_name}: Java parse error: {e}")

            # Parse configs
            try:
                hocon_map, resolved = self._config_parser.parse_project_configs(project_dir)
                self.add_config_entries(resolved, project_name, workspace_path)
            except Exception as e:
                errors.append(f"[E] {project_name}: Config parse error: {e}")

        # Cross-project URL matching
        xlinks = self.link_by_url()

        duration = time.monotonic() - start
        node_counts = self._count_by_attr("type", is_node=True)
        edge_counts = self._count_by_attr("type", is_node=False)

        self._metadata = {
            "build_time": datetime.now(timezone.utc),
            "projects": projects,
            "workspace_path": str(workspace_path),
        }

        return BuildResult(
            success=True,
            node_counts=node_counts,
            edge_counts=edge_counts,
            cross_project_links=xlinks,
            build_duration_seconds=duration,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Add nodes/edges
    # ------------------------------------------------------------------

    def _add_project_node(self, name: str) -> None:
        nid = f"Project:{name}"
        self.graph.add_node(nid, type=NodeType.PROJECT.value, name=name, project=name)

    def add_flask_endpoints(
        self, endpoints: list[FlaskEndpoint], project: str, ws: Path
    ) -> None:
        for ep in endpoints:
            rel_path = normalize_path(Path(ep.file_path), ws)
            # File node
            fid = f"File:{rel_path}"
            self.graph.add_node(
                fid, type=NodeType.FILE.value, name=rel_path,
                file_path=rel_path, project=project,
            )
            self.graph.add_edge(
                f"Project:{project}", fid, type=EdgeType.DEFINES.value,
            )
            # Function node
            func_id = f"Function:{rel_path}:{ep.function_name}"
            self.graph.add_node(
                func_id, type=NodeType.FUNCTION.value, name=ep.function_name,
                file_path=rel_path, line_number=ep.line_number, project=project,
            )
            self.graph.add_edge(fid, func_id, type=EdgeType.DEFINES.value)
            # Endpoint node
            ep_id = f"FlaskEndpoint:{ep.http_method}:{ep.full_url}"
            self.graph.add_node(
                ep_id, type=NodeType.FLASK_ENDPOINT.value,
                name=f"{ep.http_method} {ep.full_url}",
                file_path=rel_path, line_number=ep.line_number,
                project=project,
                metadata={
                    "http_method": ep.http_method,
                    "full_url": ep.full_url,
                    "namespace": ep.namespace,
                    "function_name": ep.function_name,
                },
            )
            self.graph.add_edge(func_id, ep_id, type=EdgeType.HANDLES.value)

    def add_java_nodes(
        self, nodes: list[JavaNode], project: str, ws: Path
    ) -> None:
        for jn in nodes:
            rel_path = normalize_path(Path(jn.file_path), ws)
            # File node
            fid = f"File:{rel_path}"
            self.graph.add_node(
                fid, type=NodeType.FILE.value, name=rel_path,
                file_path=rel_path, project=project,
            )
            self.graph.add_edge(f"Project:{project}", fid, type=EdgeType.DEFINES.value)
            # Java type node
            node_type = _java_file_type_to_node_type(jn.file_type)
            jid = f"{node_type.value}:{jn.class_name}"
            self.graph.add_node(
                jid, type=node_type.value, name=jn.class_name,
                file_path=rel_path, project=project,
                metadata={"methods": [m.name for m in jn.methods]},
            )
            self.graph.add_edge(fid, jid, type=EdgeType.DEFINES.value)
            # Method call edges
            for method in jn.methods:
                for call in method.calls:
                    self._add_java_call_edge(jid, jn, call, method)

    def _add_java_call_edge(self, source_id: str, jn: JavaNode, call: str, method) -> None:
        """Add edges for Java method calls in impact direction.

        Impact flows: Task → Test (if test calls task method)
                     Task → Qst (called_by)
                     Qst → Entity (uses_entity)
        """
        for nid, data in list(self.graph.nodes(data=True)):
            if data.get("type") not in (
                NodeType.JAVA_TASK.value, NodeType.JAVA_QST.value,
                NodeType.JAVA_ENTITY.value, NodeType.JAVA_TEST.value,
            ):
                continue
            methods = data.get("metadata", {}).get("methods", [])
            if call in methods and nid != source_id:
                edge_type = _infer_edge_type(jn.file_type, data["type"])
                if edge_type:
                    # Reverse for test_calls: make it Task → Test (impact direction)
                    if edge_type == EdgeType.TEST_CALLS:
                        self.graph.add_edge(nid, source_id, type=edge_type.value)
                    else:
                        self.graph.add_edge(source_id, nid, type=edge_type.value)

    def add_config_entries(
        self, configs: list[ResolvedConfig], project: str, ws: Path
    ) -> None:
        for cfg in configs:
            rel_java = normalize_path(Path(cfg.java_file), ws)
            cid = f"ConfigEntry:{cfg.config_key}"
            self.graph.add_node(
                cid, type=NodeType.CONFIG_ENTRY.value, name=cfg.config_key,
                file_path=rel_java, line_number=cfg.line_number, project=project,
                metadata={"config_key": cfg.config_key, "resolved_url": cfg.resolved_url},
            )
            # resolves_to edge: ConfigEntry → Task (impact direction)
            # Link to Tasks whose method names match the config key.
            # e.g. config_key="user.getUser" → last part "getUser"
            #      Task method "callGetUser" contains "getUser" (case-insensitive)
            key_hint = cfg.config_key.split(".")[-1].lower()  # e.g. "getuser"
            for nid, data in list(self.graph.nodes(data=True)):
                if (data.get("type") != NodeType.JAVA_TASK.value
                        or data.get("project") != project):
                    continue
                task_methods = data.get("metadata", {}).get("methods", [])
                if any(key_hint in m.lower() for m in task_methods):
                    self.graph.add_edge(cid, nid, type=EdgeType.RESOLVES_TO.value)

    def _add_function_calls(
        self, calls: list[FunctionCall], project: str, ws: Path
    ) -> None:
        for fc in calls:
            rel_path = normalize_path(Path(fc.file_path), ws)
            caller_id = f"Function:{rel_path}:{fc.caller}"
            callee_id = f"Function:{rel_path}:{fc.callee}"
            if self.graph.has_node(caller_id) and self.graph.has_node(callee_id):
                self.graph.add_edge(
                    caller_id, callee_id,
                    type=EdgeType.DEFINES.value,
                    source_line=fc.line_number,
                )

    # ------------------------------------------------------------------
    # URL matching
    # ------------------------------------------------------------------

    def link_by_url(self) -> int:
        """Exact-match Flask endpoint URLs with config resolved URLs."""
        flask_urls: dict[str, str] = {}  # url -> node_id
        for nid, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.FLASK_ENDPOINT.value:
                url = data.get("metadata", {}).get("full_url", "")
                if url:
                    flask_urls[url] = nid

        count = 0
        for nid, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.CONFIG_ENTRY.value:
                url = data.get("metadata", {}).get("resolved_url", "")
                if url in flask_urls:
                    # Impact direction: FlaskEndpoint → ConfigEntry
                    self.graph.add_edge(flask_urls[url], nid, type=EdgeType.CALLS_API.value)
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        state = GraphState(
            graph=self.graph,
            version=GRAPH_VERSION,
            build_time=getattr(self, "_metadata", {}).get(
                "build_time", datetime.now(timezone.utc)
            ),
            projects=getattr(self, "_metadata", {}).get("projects", []),
            workspace_path=getattr(self, "_metadata", {}).get("workspace_path", ""),
        )
        with open(path, "wb") as f:
            pickle.dump(state, f)

    def load(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            with open(path, "rb") as f:
                state: GraphState = pickle.load(f)
            if not hasattr(state, "version") or state.version != GRAPH_VERSION:
                logger.warning("Graph version mismatch, please rebuild")
                return False
            self.graph = state.graph
            self._metadata = {
                "build_time": state.build_time,
                "projects": state.projects,
                "workspace_path": state.workspace_path,
            }
            return True
        except Exception as exc:
            logger.warning("Failed to load graph from %s: %s", path, exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_by_attr(self, attr: str, is_node: bool) -> dict[str, int]:
        counts: dict[str, int] = {}
        items = self.graph.nodes(data=True) if is_node else self.graph.edges(data=True)
        for item in items:
            data = item[-1] if isinstance(item[-1], dict) else {}
            val = data.get(attr, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts


def _java_file_type_to_node_type(ft) -> NodeType:
    from kg_mcp.graph.models import FileType
    return {
        FileType.TEST: NodeType.JAVA_TEST,
        FileType.TASK: NodeType.JAVA_TASK,
        FileType.QST: NodeType.JAVA_QST,
        FileType.ENTITY: NodeType.JAVA_ENTITY,
        FileType.CONFIG: NodeType.CONFIG_ENTRY,
    }.get(ft, NodeType.FILE)


def _infer_edge_type(source_ft, target_type_str: str) -> EdgeType | None:
    from kg_mcp.graph.models import FileType
    mapping = {
        (FileType.TEST, NodeType.JAVA_TASK.value): EdgeType.TEST_CALLS,
        (FileType.TASK, NodeType.JAVA_QST.value): EdgeType.CALLED_BY,
        (FileType.QST, NodeType.JAVA_ENTITY.value): EdgeType.USES_ENTITY,
    }
    return mapping.get((source_ft, target_type_str))
