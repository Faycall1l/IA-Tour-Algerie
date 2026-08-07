"""Agent security — tool permissions, least agency, identity scoping.

Standard: OWASP ASI01–ASI10, Moai Standard Layer 8.

Every tool is classified by risk level. Agent runs are scoped to the
calling user's identity. Write operations require elevated permissions.
"""

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class ToolRisk(StrEnum):
    """Risk classification for agent tools."""

    READ = "read"  # No side effects, read-only queries
    WRITE = "write"  # Creates/modifies data
    EXTERNAL = "external"  # Calls external APIs (weather, transport)
    DESTRUCTIVE = "destructive"  # Deletes data, irreversible


# ── Tool risk registry ──
# Maps tool function names to their risk levels.
TOOL_RISK_MAP: dict[str, ToolRisk] = {
    # Read-only tools
    "search_pois": ToolRisk.READ,
    "search_stays": ToolRisk.READ,
    "search_experiences": ToolRisk.READ,
    "search_artisans": ToolRisk.READ,
    "get_wilaya_guide": ToolRisk.READ,
    "find_events": ToolRisk.READ,
    "get_operator_contacts": ToolRisk.READ,
    # External API tools
    "get_weather": ToolRisk.EXTERNAL,
    "get_transport_route": ToolRisk.EXTERNAL,
    # Memory tools — agent-controlled writes to persistent memory; scoped
    # to the session, so classified as write (never destructive).
    "remember": ToolRisk.WRITE,
    "recall": ToolRisk.READ,
    # Write tools
    "create_trip": ToolRisk.WRITE,
    "add_trip_item": ToolRisk.WRITE,
    "update_trip": ToolRisk.WRITE,
    # Destructive tools (should never be agent-callable in production)
    "delete_trip": ToolRisk.DESTRUCTIVE,
    "delete_user": ToolRisk.DESTRUCTIVE,
}


# ── Role-based tool permissions ──

ROLE_TOOL_PERMISSIONS: dict[str, set[ToolRisk]] = {
    "traveler": {ToolRisk.READ, ToolRisk.EXTERNAL},
    "guide": {ToolRisk.READ, ToolRisk.EXTERNAL, ToolRisk.WRITE},
    "agency": {ToolRisk.READ, ToolRisk.EXTERNAL, ToolRisk.WRITE},
    "hotel": {ToolRisk.READ, ToolRisk.EXTERNAL, ToolRisk.WRITE},
    "admin": {ToolRisk.READ, ToolRisk.EXTERNAL, ToolRisk.WRITE, ToolRisk.DESTRUCTIVE},
    "artisan": {ToolRisk.READ, ToolRisk.EXTERNAL},
}


def can_use_tool(role: str, tool_name: str) -> bool:
    """Check if a user role is allowed to invoke a specific tool."""
    risk = TOOL_RISK_MAP.get(tool_name, ToolRisk.READ)
    allowed_risks = ROLE_TOOL_PERMISSIONS.get(role, set())
    return risk in allowed_risks


def get_tool_risk(tool_name: str) -> ToolRisk:
    """Get the risk classification for a tool."""
    return TOOL_RISK_MAP.get(tool_name, ToolRisk.READ)


def require_tool_permission(role: str, tool_name: str) -> None:
    """Raise if role cannot use tool. Logs the attempt."""
    if not can_use_tool(role, tool_name):
        risk = get_tool_risk(tool_name)
        logger.warning(
            "SECURITY: role=%s blocked from tool=%s (risk=%s)",
            role,
            tool_name,
            risk.value,
        )
        raise PermissionError(
            f"Role '{role}' does not have permission to use tool '{tool_name}' "
            f"(risk level: {risk.value})"
        )
