"""Runbook: restart a systemd service via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class RestartServiceRunbook(Runbook):
    """Restart a systemd service on a remote host.

    Tools are pre-bound to the target host by execute_node — no host params needed.

    Params:
        service: Name of the systemd service (e.g. "apache2", "mariadb").
    """

    name = "restart_service"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        service = params.get("service", "")
        if not service:
            return RunbookResult(success=False, message="Параметр 'service' не указан")

        restart_tool = self._get_tool("ssh_systemctl_restart")
        response = await restart_tool.ainvoke({"service": service})

        exit_code = response.get("exit_code", 0)
        stderr = response.get("stderr", "")
        stdout = response.get("stdout", "")

        if exit_code == 0:
            return RunbookResult(
                success=True,
                message=f"Сервис {service} успешно перезапущен",
                details=stdout,
            )
        else:
            return RunbookResult(
                success=False,
                message=f"Не удалось перезапустить сервис {service}",
                details=stderr or stdout,
            )
