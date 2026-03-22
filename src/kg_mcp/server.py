"""MCP Server entry point - registers 5 tools and handles stdio transport."""

import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from kg_mcp.graph.analyzer import ImpactAnalyzer
from kg_mcp.graph.builder import GraphBuilder
from kg_mcp.graph.models import GraphStatus
from kg_mcp.output.formatter import CompactFormatter
from kg_mcp.utils import get_cache_dir

# Log to stderr to avoid interfering with stdio transport
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("kg-multi-project-mcp")
builder = GraphBuilder()
formatter = CompactFormatter()

# Try to load persisted graph on startup
_cache_dir = get_cache_dir()
_pickle_path = _cache_dir / "graph.pkl"
_config_path = _cache_dir / "workspace.json"

if builder.load(_pickle_path):
    logger.info("Loaded graph from %s", _pickle_path)
else:
    logger.info("No persisted graph found, starting fresh")


def _get_analyzer() -> ImpactAnalyzer:
    return ImpactAnalyzer(builder.graph)


def _is_graph_built() -> bool:
    return len(builder.graph.nodes) > 0


def _save_workspace_config(workspace_path: str, projects: list[str]) -> None:
    try:
        config = {"workspace_path": workspace_path, "projects": projects}
        with open(_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to save workspace config: %s", exc)


# ------------------------------------------------------------------
# MCP Tools
# ------------------------------------------------------------------


@mcp.tool()
async def build_graph(workspace_path: str) -> str:
    """Build the Knowledge Graph by scanning all projects in the workspace.

    Parses Flask endpoints, Java Serenity BDD files, and HOCON configs.
    Creates cross-project links via URL matching.

    Args:
        workspace_path: Absolute path to the workspace directory containing projects.
    """
    ws = Path(workspace_path)
    if not ws.is_dir():
        return f"BUILD FAIL | 0.0s\nerrors: 1\n  [E] Workspace path does not exist: {workspace_path}"

    result = builder.build(ws)
    if result.success:
        builder.save(_pickle_path)
        projects = getattr(builder, "_metadata", {}).get("projects", [])
        _save_workspace_config(workspace_path, projects)
        return formatter.format_build_with_projects(result, projects)
    return formatter.format_build(result)


@mcp.tool()
async def query_impact(name: str, max_depth: int = 10) -> str:
    """Query the impact chain of a function or endpoint.

    Finds all files/functions affected by changes to the given function or endpoint.

    Args:
        name: Function name, endpoint URL, or endpoint name to query.
        max_depth: Maximum traversal depth (default 10).
    """
    if not _is_graph_built():
        return "STATUS: not_built\nhint: call build_graph(workspace_path) first"

    analyzer = _get_analyzer()
    result = analyzer.query_impact(name, max_depth)
    if result is None:
        suggestions = analyzer.suggest_similar(name)
        return formatter.format_not_found(name, suggestions)
    return formatter.format_impact(result)


@mcp.tool()
async def list_apis(project: str | None = None) -> str:
    """List all Flask API endpoints in the Knowledge Graph.

    Args:
        project: Optional project name to filter by. If None, list all.
    """
    if not _is_graph_built():
        return "STATUS: not_built\nhint: call build_graph(workspace_path) first"

    analyzer = _get_analyzer()
    apis = analyzer.list_apis(project)
    return formatter.format_api_list(apis)


@mcp.tool()
async def find_callers(api_url: str) -> str:
    """Find all callers (Task/Test/Qst) that reference a given API URL.

    Args:
        api_url: The API URL to search for callers.
    """
    if not _is_graph_built():
        return "STATUS: not_built\nhint: call build_graph(workspace_path) first"

    analyzer = _get_analyzer()
    callers = analyzer.find_callers(api_url)
    if callers is None:
        suggestions = analyzer.suggest_similar(api_url)
        return formatter.format_not_found(api_url, suggestions)
    return formatter.format_callers(api_url, callers)


@mcp.tool()
async def graph_status() -> str:
    """Check the current status of the Knowledge Graph."""
    if not _is_graph_built():
        return formatter.format_status(GraphStatus(is_built=False))

    metadata = getattr(builder, "_metadata", {})
    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}

    for _, data in builder.graph.nodes(data=True):
        t = data.get("type", "unknown")
        node_counts[t] = node_counts.get(t, 0) + 1
    for _, _, data in builder.graph.edges(data=True):
        t = data.get("type", "unknown")
        edge_counts[t] = edge_counts.get(t, 0) + 1

    pickle_size = None
    pickle_time = None
    if _pickle_path.exists():
        pickle_size = _pickle_path.stat().st_size
        from datetime import datetime, timezone
        pickle_time = datetime.fromtimestamp(
            _pickle_path.stat().st_mtime, tz=timezone.utc
        )

    return formatter.format_status(GraphStatus(
        is_built=True,
        node_counts=node_counts,
        edge_counts=edge_counts,
        last_build_time=metadata.get("build_time"),
        projects=metadata.get("projects", []),
        pickle_size_bytes=pickle_size,
        pickle_save_time=pickle_time,
    ))


def main() -> None:
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
