"""Runbook: show MySQL/MariaDB full processlist via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class MysqlProcesslistRunbook(Runbook):
    """Show the full MySQL/MariaDB processlist.

    Read-only runbook. Uses ssh_mysql_exec tool to run SHOW FULL PROCESSLIST.
    Tools are pre-bound to the target host.
    """

    name = "mysql_processlist"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_mysql_exec")

        output = await tool.ainvoke({"query": "SHOW FULL PROCESSLIST"})

        return RunbookResult(
            success=True,
            message="MySQL/MariaDB processlist",
            details=output,
        )
