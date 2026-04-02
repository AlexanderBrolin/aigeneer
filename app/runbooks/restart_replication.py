"""Runbook: restart MariaDB replication via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class RestartReplicationRunbook(Runbook):
    """Restart MariaDB replication on a remote host.

    Executes STOP SLAVE; START SLAVE; then verifies with SHOW SLAVE STATUS.

    Params:
        host: Target hostname or IP.
        ssh_user: SSH username.
        ssh_key_path: Path to SSH private key.
        ssh_port: SSH port (default 22).
    """

    name = "restart_replication"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        host = params["host"]
        ssh_user = params.get("ssh_user", "deploy")
        ssh_key_path = params.get("ssh_key_path", "")
        ssh_port = params.get("ssh_port", 22)

        # Step 1: Stop and start replication
        restart_result = await tool.ainvoke({
            "host": host,
            "command": 'mysql -e "STOP SLAVE; START SLAVE;"',
            "ssh_user": ssh_user,
            "ssh_key_path": ssh_key_path,
            "ssh_port": ssh_port,
        })

        if restart_result.get("exit_code", 1) != 0:
            return RunbookResult(
                success=False,
                message=f"Не удалось перезапустить репликацию на {host}",
                details=restart_result.get("stderr", "") or restart_result.get("stdout", ""),
            )

        # Step 2: Check replication status
        status_result = await tool.ainvoke({
            "host": host,
            "command": 'mysql -e "SHOW SLAVE STATUS\\G"',
            "ssh_user": ssh_user,
            "ssh_key_path": ssh_key_path,
            "ssh_port": ssh_port,
        })

        stdout = status_result.get("stdout", "")

        io_running = "Slave_IO_Running: Yes" in stdout
        sql_running = "Slave_SQL_Running: Yes" in stdout

        if io_running and sql_running:
            return RunbookResult(
                success=True,
                message=f"Репликация на {host} успешно перезапущена",
                details=stdout,
            )
        else:
            return RunbookResult(
                success=False,
                message=f"Репликация на {host} перезапущена, но статус неудовлетворительный",
                details=stdout,
            )
