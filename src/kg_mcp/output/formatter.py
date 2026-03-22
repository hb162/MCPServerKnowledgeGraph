"""Compact text formatter optimized for LLM context window."""

from datetime import datetime

from kg_mcp.graph.models import (
    ApiInfo,
    BuildResult,
    CallerInfo,
    GraphStatus,
    ImpactResult,
)


class CompactFormatter:
    """Format query results as compact text (not JSON) for LLM consumption."""

    @staticmethod
    def format_build(result: BuildResult) -> str:
        if not result.success:
            lines = [f"BUILD FAIL | {result.build_duration_seconds:.1f}s"]
            if result.errors:
                lines.append(f"errors: {len(result.errors)}")
                for e in result.errors:
                    lines.append(f"  {e}")
            if result.warnings:
                lines.append(f"warnings: {len(result.warnings)}")
                for w in result.warnings:
                    lines.append(f"  [W] {w}")
            return "\n".join(lines)

        nodes_str = " ".join(f"{k}={v}" for k, v in result.node_counts.items())
        edges_str = " ".join(f"{k}={v}" for k, v in result.edge_counts.items())
        lines = [
            f"BUILD OK | {result.build_duration_seconds:.1f}s",
            f"nodes: {nodes_str}",
            f"edges: {edges_str}",
            f"xlinks: {result.cross_project_links}",
            f"projects: {' '.join(sorted(set()))}",  # filled by caller
        ]
        return "\n".join(lines)

    @staticmethod
    def format_build_with_projects(result: BuildResult, projects: list[str]) -> str:
        if not result.success:
            return CompactFormatter.format_build(result)
        nodes_str = " ".join(f"{k}={v}" for k, v in result.node_counts.items())
        edges_str = " ".join(f"{k}={v}" for k, v in result.edge_counts.items())
        return "\n".join([
            f"BUILD OK | {result.build_duration_seconds:.1f}s",
            f"nodes: {nodes_str}",
            f"edges: {edges_str}",
            f"xlinks: {result.cross_project_links}",
            f"projects: {' '.join(projects)}",
        ])

    @staticmethod
    def format_impact(result: ImpactResult) -> str:
        url_part = f" → {result.source_url}" if result.source_url else ""
        lines = [
            f"IMPACT: {result.source_name}(){url_part}",
            f"  src: {result.source_file}:{result.source_line}",
        ]
        for chain in result.chains:
            lines.append("CHAIN:")
            for step in chain.steps:
                lines.append(
                    f"  → {step.file_path}:{step.line_number} "
                    f"{step.name} [{step.edge_type}]"
                )
        lines.append(
            f"SUMMARY: {result.summary.total_files} files | "
            f"{result.summary.total_projects} projects | "
            f"depth={result.summary.max_depth}"
        )
        return "\n".join(lines)

    @staticmethod
    def format_not_found(name: str, suggestions: list[str]) -> str:
        lines = [f"NOT FOUND: {name}"]
        if suggestions:
            lines.append(f"SIMILAR: {' '.join(suggestions)}")
        return "\n".join(lines)

    @staticmethod
    def format_callers(api_url: str, callers: list[CallerInfo]) -> str:
        if not callers:
            return f"NO CALLERS: {api_url}"
        lines = [f"CALLERS: {api_url} | {len(callers)} callers"]
        for c in callers:
            lines.append(
                f"  [{c.caller_type}] {c.caller_name}  "
                f"{c.file_path}:{c.line_number}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_api_list(apis: list[ApiInfo]) -> str:
        if not apis:
            return "APIS: 0 endpoints"
        projects = sorted(set(a.project for a in apis))
        lines = [f"APIS: {len(apis)} endpoints | {len(projects)} projects"]
        for proj in projects:
            lines.append(f"[{proj}]")
            proj_apis = [a for a in apis if a.project == proj]
            for a in proj_apis:
                lines.append(
                    f"  {a.http_method:<5} {a.full_url:<35} "
                    f"{a.function_name}()  {a.file_path}"
                )
        return "\n".join(lines)

    @staticmethod
    def format_status(status: GraphStatus) -> str:
        if not status.is_built:
            return "STATUS: not_built\nhint: call build_graph(workspace_path) first"
        lines = [
            "STATUS: built",
            f"built: {status.last_build_time.isoformat() if status.last_build_time else 'unknown'}",
        ]
        if status.node_counts:
            total = sum(status.node_counts.values())
            detail = " ".join(f"{k}={v}" for k, v in status.node_counts.items())
            lines.append(f"nodes: {total} ({detail})")
        if status.edge_counts:
            total = sum(status.edge_counts.values())
            detail = " ".join(f"{k}={v}" for k, v in status.edge_counts.items())
            lines.append(f"edges: {total} ({detail})")
        if status.projects:
            lines.append(f"projects: {' '.join(status.projects)}")
        if status.pickle_size_bytes is not None:
            size_kb = status.pickle_size_bytes / 1024
            lines.append(f"cache: ({size_kb:.1f}KB)")
        return "\n".join(lines)
