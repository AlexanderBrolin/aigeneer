"""Runbook: restart MariaDB replication via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class RestartReplicationRunbook(Runbook):
    """Restart MariaDB replication on a remote host.

    Executes STOP SLAVE; START SLAVE; then verifies with SHOW SLAVE STATUS.
    Tools are pre-bound to the target host by execute_node — no host params needed.
    """

    name = "restart_replication"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        # Step 1: Stop and start replication
        await tool.ainvoke({"command": 'mysql -e "STOP SLAVE; START SLAVE;"'})

        # Step 2: Verify replication status
        status = await tool.ainvoke({"command": 'mysql -e "SHOW SLAVE STATUS\\G"'})

        io_running = "Slave_IO_Running: Yes" in status
        sql_running = "Slave_SQL_Running: Yes" in status

        if io_running and sql_running:
            return RunbookResult(
                success=True,
                message="Репликация успешно перезапущена",
                details=status,
            )
        else:
            return RunbookResult(
                success=False,
                message="Репликация перезапущена, но статус неудовлетворительный",
                details=status or "(пустой вывод SHOW SLAVE STATUS)",
            )
