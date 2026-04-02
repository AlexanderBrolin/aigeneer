"""Runbook: show current MariaDB replication status via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class ShowReplicationStatusRunbook(Runbook):
    """Show current MariaDB replication status (SHOW SLAVE STATUS).

    Read-only runbook. Tools are pre-bound to the target host.
    """

    name = "show_replication_status"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        output = await tool.ainvoke({"command": 'mysql -e "SHOW SLAVE STATUS\\G"'})

        if not output or not output.strip():
            return RunbookResult(
                success=True,
                message="Репликация не настроена (SHOW SLAVE STATUS пуст)",
                details="",
            )

        io_running = "Slave_IO_Running: Yes" in output
        sql_running = "Slave_SQL_Running: Yes" in output

        if io_running and sql_running:
            status_line = "IO: ✅  SQL: ✅ — репликация работает"
        else:
            io_str = "✅" if io_running else "❌"
            sql_str = "✅" if sql_running else "❌"
            status_line = f"IO: {io_str}  SQL: {sql_str} — репликация остановлена"

        return RunbookResult(
            success=True,
            message=f"Статус репликации: {status_line}",
            details=output,
        )
