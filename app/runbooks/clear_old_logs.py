"""Runbook: clear old rotated log files via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class ClearOldLogsRunbook(Runbook):
    """Delete old rotated log files on a remote host.

    Uses find to delete *.log.* files older than N days.
    Tools are pre-bound to the target host — no host params needed.

    Params:
        log_path: Directory to search for old logs (e.g. "/var/log/apache2").
        older_than_days: Delete files older than this many days.
    """

    name = "clear_old_logs"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        log_path = params.get("log_path", "/var/log")
        older_than_days = params.get("older_than_days", 30)

        command = self._sudo(f'find {log_path} -name "*.log.*" -mtime +{older_than_days} -delete -print')
        response = await tool.ainvoke({"command": command})

        exit_code = response.get("exit_code", 0)
        stdout = response.get("stdout", "")
        stderr = response.get("stderr", "")

        if exit_code != 0:
            return RunbookResult(
                success=False,
                message=f"Ошибка при удалении логов в {log_path}",
                details=stderr or stdout,
            )

        deleted = [line for line in stdout.splitlines() if line.strip()]
        return RunbookResult(
            success=True,
            message=f"Удалено {len(deleted)} файлов логов старше {older_than_days} дней в {log_path}",
            details=stdout or "(файлов для удаления не найдено)",
        )
