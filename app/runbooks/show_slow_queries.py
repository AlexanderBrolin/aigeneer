"""Runbook: show recent slow queries from MariaDB slow query log."""

from app.runbooks.base import Runbook, RunbookResult


class ShowSlowQueriesRunbook(Runbook):
    """Show the tail of the MariaDB slow query log.

    Read-only runbook. Tools are pre-bound to the target host.

    Params:
        lines: Number of lines to tail (default 50).
        log_path: Path to slow query log (default /var/log/mysql/slow.log).
    """

    name = "show_slow_queries"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        lines = params.get("lines", 50)
        log_path = params.get("log_path", "/var/log/mysql/slow.log")

        output = await tool.ainvoke({"command": f"tail -n {lines} {log_path}"})

        if not output or not output.strip():
            return RunbookResult(
                success=True,
                message=f"Медленных запросов нет (или файл {log_path} пуст)",
                details="",
            )

        return RunbookResult(
            success=True,
            message=f"Последние {lines} строк {log_path}",
            details=output,
        )
