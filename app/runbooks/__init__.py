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
from app.runbooks.check_backup import CheckBackupRunbook
from app.runbooks.free_memory import FreeMemoryRunbook
from app.runbooks.kill_process import KillProcessRunbook
from app.runbooks.mysql_processlist import MysqlProcesslistRunbook
from app.runbooks.rotate_logs import RotateLogsRunbook
from app.runbooks.show_connections import ShowConnectionsRunbook
from app.runbooks.show_disk_usage import ShowDiskUsageRunbook
from app.runbooks.show_top_processes import ShowTopProcessesRunbook

RUNBOOK_REGISTRY: dict[str, type[Runbook]] = {
    "restart_service": RestartServiceRunbook,
    "restart_replication": RestartReplicationRunbook,
    "clear_old_logs": ClearOldLogsRunbook,
    "show_slow_queries": ShowSlowQueriesRunbook,
    "show_replication_status": ShowReplicationStatusRunbook,
    "show_top_processes": ShowTopProcessesRunbook,
    "show_connections": ShowConnectionsRunbook,
    "show_disk_usage": ShowDiskUsageRunbook,
    "mysql_processlist": MysqlProcesslistRunbook,
    "check_backup": CheckBackupRunbook,
    "rotate_logs": RotateLogsRunbook,
    "kill_process": KillProcessRunbook,
    "free_memory": FreeMemoryRunbook,
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
