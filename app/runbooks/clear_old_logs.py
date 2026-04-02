"""Runbook: clear old rotated log files via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class ClearOldLogsRunbook(Runbook):
    """Delete old rotated log files on a remote host.

    Uses find to delete *.log.* files older than N days.

    Params:
        host: Target hostname or IP.
        log_path: Directory to search for old logs (e.g. "/var/log/apache2").
        older_than_days: Delete files older than this many days.
        ssh_user: SSH username.
        ssh_key_path: Path to SSH private key.
        ssh_port: SSH port (default 22).
    """

    name = "clear_old_logs"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        host = params["host"]
        log_path = params["log_path"]
        older_than_days = params["older_than_days"]

        command = f'find {log_path} -name "*.log.*" -mtime +{older_than_days} -delete'

        result = await tool.ainvoke({
            "host": host,
            "command": command,
            "ssh_user": params.get("ssh_user", "deploy"),
            "ssh_key_path": params.get("ssh_key_path", ""),
            "ssh_port": params.get("ssh_port", 22),
        })

        exit_code = result.get("exit_code", 1)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")

        if exit_code == 0:
            return RunbookResult(
                success=True,
                message=f"Старые логи в {log_path} на {host} удалены (старше {older_than_days} дней)",
                details=stdout,
            )
        else:
            return RunbookResult(
                success=False,
                message=f"Не удалось удалить старые логи в {log_path} на {host}",
                details=stderr or stdout,
            )
