"""Runbook system: deterministic scripts for server actions.

Runbooks are NOT LLM-driven. Each runbook is a function that knows
exactly what to do via SSH/MCP tools.
"""

from app.runbooks.base import Runbook, RunbookResult
from app.runbooks.restart_service import RestartServiceRunbook
from app.runbooks.restart_replication import RestartReplicationRunbook
from app.runbooks.clear_old_logs import ClearOldLogsRunbook
from app.runbooks.show_slow_queries import ShowSlowQueriesRunbook
from app.runbooks.show_replication_status import ShowReplicationStatusRunbook

RUNBOOK_REGISTRY: dict[str, type[Runbook]] = {
    "restart_service": RestartServiceRunbook,
    "restart_replication": RestartReplicationRunbook,
    "clear_old_logs": ClearOldLogsRunbook,
    "show_slow_queries": ShowSlowQueriesRunbook,
    "show_replication_status": ShowReplicationStatusRunbook,
}


async def run_runbook(name: str, params: dict, tools: list) -> RunbookResult:
    """Look up and execute a runbook by name.

    Args:
        name: Runbook name from RUNBOOK_REGISTRY.
        params: Parameters to pass to the runbook.
        tools: List of MCP tools available for execution.

    Returns:
        RunbookResult with success/failure status and details.
    """
    cls = RUNBOOK_REGISTRY.get(name)
    if not cls:
        return RunbookResult(success=False, message=f"Runbook `{name}` не найден")
    return await cls(tools).execute(params)
