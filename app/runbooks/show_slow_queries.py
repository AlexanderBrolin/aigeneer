"""Runbook: show recent slow queries from MariaDB slow query log."""

from app.runbooks.base import Runbook, RunbookResult


class ShowSlowQueriesRunbook(Runbook):
    """Show the tail of the MariaDB slow query log.

    This is a read-only runbook that does not modify anything.

    Params:
        host: Target hostname or IP.
        lines: Number of lines to tail (default 50).
        log_path: Path to slow query log (default /var/log/mysql/slow.log).
        ssh_user: SSH username.
        ssh_key_path: Path to SSH private key.
        ssh_port: SSH port (default 22).
    """

    name = "show_slow_queries"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        host = params["host"]
        lines = params.get("lines", 50)
        log_path = params.get("log_path", "/var/log/mysql/slow.log")

        command = f"tail -n {lines} {log_path}"

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
                message=f"Медленные запросы с {host} ({log_path}, последние {lines} строк)",
                details=stdout,
            )
        else:
            return RunbookResult(
                success=False,
                message=f"Не удалось прочитать лог медленных запросов на {host}",
                details=stderr or stdout,
            )
