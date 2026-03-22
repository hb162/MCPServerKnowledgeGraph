"""Impact analyzer - query the Knowledge Graph for impact chains and callers."""

import difflib
from collections import deque

import networkx as nx

from kg_mcp.graph.models import (
    ApiInfo,
    CallerInfo,
    EdgeType,
    GraphStatus,
    ImpactChain,
    ImpactResult,
    ImpactStep,
    ImpactSummary,
    NodeType,
)


class ImpactAnalyzer:
    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # query_impact: BFS traversal from a source node
    # ------------------------------------------------------------------

    def query_impact(self, name: str, max_depth: int = 10) -> ImpactResult | None:
        """Find all nodes reachable from a function/endpoint by name."""
        source_id = self._find_node_by_name(name)
        if source_id is None:
            return None

        data = self.graph.nodes[source_id]
        source_url = data.get("metadata", {}).get("full_url")
        chains = self._bfs_chains(source_id, max_depth)

        # Collect unique files and projects
        files: set[str] = set()
        projects: set[str] = set()
        max_d = 0
        for chain in chains:
            for step in chain.steps:
                files.add(step.file_path)
            if chain.steps:
                max_d = max(max_d, len(chain.steps))
        for nid in self.graph.nodes:
            nd = self.graph.nodes[nid]
            if nd.get("file_path") in files:
                projects.add(nd.get("project", ""))

        return ImpactResult(
            source_name=data.get("name", name),
            source_url=source_url,
            source_file=data.get("file_path", ""),
            source_line=data.get("line_number", 0),
            chains=chains,
            summary=ImpactSummary(
                total_files=len(files),
                total_projects=len(projects - {""}),
                max_depth=max_d,
            ),
        )

    def _bfs_chains(self, source_id: str, max_depth: int) -> list[ImpactChain]:
        """BFS from source, return all impact chains."""
        visited: set[str] = {source_id}
        queue: deque[tuple[str, list[ImpactStep]]] = deque()

        # Seed with direct successors
        for _, target, edata in self.graph.out_edges(source_id, data=True):
            if target not in visited:
                tdata = self.graph.nodes[target]
                step = ImpactStep(
                    name=tdata.get("name", target),
                    file_path=tdata.get("file_path", ""),
                    line_number=tdata.get("line_number", 0),
                    edge_type=edata.get("type", ""),
                )
                queue.append((target, [step]))

        chains: list[ImpactChain] = []
        while queue:
            current, path = queue.popleft()
            if len(path) > max_depth:
                continue
            visited.add(current)

            successors = [
                (t, ed) for _, t, ed in self.graph.out_edges(current, data=True)
                if t not in visited
            ]
            if not successors:
                # Leaf node - record the chain
                chains.append(ImpactChain(steps=path))
                continue

            for target, edata in successors:
                tdata = self.graph.nodes[target]
                step = ImpactStep(
                    name=tdata.get("name", target),
                    file_path=tdata.get("file_path", ""),
                    line_number=tdata.get("line_number", 0),
                    edge_type=edata.get("type", ""),
                )
                queue.append((target, path + [step]))

        return chains

    # ------------------------------------------------------------------
    # find_callers: reverse lookup for an API URL
    # ------------------------------------------------------------------

    def find_callers(self, api_url: str) -> list[CallerInfo] | None:
        """Find all callers (Task/Test/Qst) that call a given API URL.

        Edges now flow in impact direction (FlaskEndpoint → Config → Task → Test),
        so we walk successors from the endpoint to find affected Java nodes.
        """
        target_id = self._find_endpoint_by_url(api_url)
        if target_id is None:
            return None

        callers: list[CallerInfo] = []
        visited: set[str] = set()
        queue = deque([target_id])
        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            for succ in self.graph.successors(nid):
                if succ in visited:
                    continue
                sdata = self.graph.nodes[succ]
                stype = sdata.get("type", "")
                if stype in (
                    NodeType.JAVA_TASK.value,
                    NodeType.JAVA_TEST.value,
                    NodeType.JAVA_QST.value,
                ):
                    caller_type = stype.replace("Java", "")
                    callers.append(CallerInfo(
                        caller_name=sdata.get("name", succ),
                        caller_type=caller_type,
                        file_path=sdata.get("file_path", ""),
                        line_number=sdata.get("line_number", 0),
                    ))
                queue.append(succ)
        return callers

    # ------------------------------------------------------------------
    # list_apis: grouped by project, sorted by URL
    # ------------------------------------------------------------------

    def list_apis(self, project: str | None = None) -> list[ApiInfo]:
        """Return all Flask endpoints, grouped by project, sorted by URL."""
        apis: list[ApiInfo] = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("type") != NodeType.FLASK_ENDPOINT.value:
                continue
            proj = data.get("project", "")
            if project and proj != project:
                continue
            meta = data.get("metadata", {})
            apis.append(ApiInfo(
                http_method=meta.get("http_method", ""),
                full_url=meta.get("full_url", ""),
                function_name=meta.get("function_name", ""),
                file_path=data.get("file_path", ""),
                project=proj,
            ))
        # Sort by project, then URL alphabetically
        apis.sort(key=lambda a: (a.project, a.full_url))
        return apis

    # ------------------------------------------------------------------
    # suggest_similar: fuzzy matching for not-found names
    # ------------------------------------------------------------------

    def suggest_similar(self, name: str, threshold: float = 0.6) -> list[str]:
        """Suggest similar node names using SequenceMatcher."""
        all_names: list[str] = []
        for _, data in self.graph.nodes(data=True):
            n = data.get("name", "")
            if n:
                all_names.append(n)
        matches = difflib.get_close_matches(name, all_names, n=5, cutoff=threshold)
        return matches

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_node_by_name(self, name: str) -> str | None:
        """Find a node by function name, endpoint name, or URL."""
        for nid, data in self.graph.nodes(data=True):
            if data.get("name") == name:
                return nid
            meta = data.get("metadata", {})
            if meta.get("full_url") == name or meta.get("function_name") == name:
                return nid
        return None

    def _find_endpoint_by_url(self, url: str) -> str | None:
        """Find FlaskEndpoint or ConfigEntry node by URL."""
        for nid, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.FLASK_ENDPOINT.value:
                if data.get("metadata", {}).get("full_url") == url:
                    return nid
            if data.get("type") == NodeType.CONFIG_ENTRY.value:
                if data.get("metadata", {}).get("resolved_url") == url:
                    return nid
        # Try partial match (e.g. just the path without method)
        for nid, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.FLASK_ENDPOINT.value:
                name = data.get("name", "")
                if url in name:
                    return nid
        return None
