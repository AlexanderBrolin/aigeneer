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

        response = await tool.ainvoke({"command": 'mysql -e "SHOW SLAVE STATUS\\G"'})

        exit_code = response.get("exit_code", 0)
        stdout = response.get("stdout", "")
        stderr = response.get("stderr", "")

        if exit_code != 0:
            return RunbookResult(
                success=False,
                message="Не удалось получить статус репликации",
                details=stderr or stdout,
            )

        if not stdout or not stdout.strip():
            return RunbookResult(
                success=True,
                message="Репликация не настроена (SHOW SLAVE STATUS пуст)",
                details="",
            )

        io_running = "Slave_IO_Running: Yes" in stdout
        sql_running = "Slave_SQL_Running: Yes" in stdout

        if io_running and sql_running:
            status_line = "IO: OK  SQL: OK — репликация работает"
        else:
            io_str = "OK" if io_running else "FAIL"
            sql_str = "OK" if sql_running else "FAIL"
            status_line = f"IO: {io_str}  SQL: {sql_str} — репликация остановлена"

        return RunbookResult(
            success=True,
            message=f"Статус репликации: {status_line}",
            details=stdout,
        )
