"""Runbook: restart a systemd service via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class RestartServiceRunbook(Runbook):
    """Restart a systemd service on a remote host.

    Params:
        host: Target hostname or IP.
        service: Name of the systemd service (e.g. "apache2", "mariadb").
        ssh_user: SSH username.
        ssh_key_path: Path to SSH private key.
        ssh_port: SSH port (default 22).
    """

    name = "restart_service"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_systemctl_restart")

        result = await tool.ainvoke({
            "host": params["host"],
            "service": params["service"],
            "ssh_user": params.get("ssh_user", "deploy"),
            "ssh_key_path": params.get("ssh_key_path", ""),
            "ssh_port": params.get("ssh_port", 22),
        })

        exit_code = result.get("exit_code", 1)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        service = params["service"]
        host = params["host"]

        if exit_code == 0:
            return RunbookResult(
                success=True,
                message=f"Сервис {service} на {host} успешно перезапущен",
                details=stdout,
            )
        else:
            return RunbookResult(
                success=False,
                message=f"Не удалось перезапустить {service} на {host}",
                details=stderr or stdout,
            )
