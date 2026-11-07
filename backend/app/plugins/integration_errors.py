from __future__ import annotations


class IntegrationApprovalRequired(Exception):
    """A mutating or side-effecting integration action needs payload.approved=true."""


class IntegrationUnavailableError(Exception):
    """A local integration (MCP server, OpenJarvis, graph file, ...) is not reachable or not configured."""


class IntegrationNotFoundError(Exception):
    """A named integration resource (database, skill, node, tool) does not exist."""


def require_approval(payload: dict, message: str) -> None:
    if payload.get("approved") is not True:
        raise IntegrationApprovalRequired(message)
