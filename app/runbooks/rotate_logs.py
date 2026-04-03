"""Runbook: force log rotation via logrotate."""

from app.runbooks.base import Runbook, RunbookResult


class RotateLogsRunbook(Runbook):
    """Force log rotation for a given logrotate config.

    Runs: sudo logrotate -f /etc/logrotate.d/<config>
    Tools are pre-bound to the target host — no host params needed.

    Params:
        config: REQUIRED — name of the logrotate config file (e.g. "apache2").
    """

    name = "rotate_logs"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        config = params.get("config", "")
        if not config:
            return RunbookResult(
                success=False,
                message="Параметр 'config' не указан",
                details="",
            )

        tool = self._get_tool("ssh_exec")
        command = f"sudo logrotate -f /etc/logrotate.d/{config}"
        output = await tool.ainvoke({"command": command})

        return RunbookResult(
            success=True,
            message=f"Ротация логов для {config} выполнена",
            details=output,
        )
