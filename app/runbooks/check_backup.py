"""Runbook: check for recent backup files via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class CheckBackupRunbook(Runbook):
    """Check for recent backup files in a given directory.

    Read-only runbook. Lists backup files modified in the last 24 hours.
    Tools are pre-bound to the target host.

    Params:
        backup_path: REQUIRED — directory to check for backup files.
        max_age_hours: Maximum age of backup files in hours (default 24).
    """

    name = "check_backup"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        backup_path = params.get("backup_path", "")
        if not backup_path:
            return RunbookResult(
                success=False,
                message="Параметр 'backup_path' не указан",
                details="",
            )

        tool = self._get_tool("ssh_exec")
        max_age_hours = params.get("max_age_hours", 24)
        # find files newer than max_age_hours
        command = f'find {backup_path} -type f -mmin -{max_age_hours * 60} | sort'

        output = await tool.ainvoke({"command": command})

        files = [line for line in output.splitlines() if line.strip()]
        if not files:
            return RunbookResult(
                success=False,
                message=f"No recent backups found in {backup_path} (last {max_age_hours}h)",
                details=output,
            )

        return RunbookResult(
            success=True,
            message=f"Найдено {len(files)} файлов резервных копий в {backup_path}",
            details=output,
        )
