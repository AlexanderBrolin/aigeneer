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
        status_tool = self._get_tool("ssh_systemctl_status")

        await restart_tool.ainvoke({"service": service})

        # Verify by checking actual service state
        state = await status_tool.ainvoke({"service": service})

        if state.strip() == "active":
            return RunbookResult(
                success=True,
                message=f"Сервис {service} успешно перезапущен",
                details=f"Текущий статус: {state.strip()}",
            )
        else:
            return RunbookResult(
                success=False,
                message=f"Сервис {service} перезапущен, но статус: {state.strip()}",
                details=state,
            )
