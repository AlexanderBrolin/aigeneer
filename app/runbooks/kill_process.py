"""Runbook: kill a process by PID via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class KillProcessRunbook(Runbook):
    """Send a signal to a process by PID on a remote host.

    Runs: sudo kill -<signal> <pid>
    Tools are pre-bound to the target host — no host params needed.

    Params:
        pid: REQUIRED — PID of the process to kill.
        signal: Signal number to send (default 15 / SIGTERM).
    """

    name = "kill_process"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        pid = params.get("pid", "")
        if not pid:
            return RunbookResult(
                success=False,
                message="Параметр 'pid' не указан",
                details="",
            )

        signal = params.get("signal", 15)
        tool = self._get_tool("ssh_exec")
        command = self._sudo(f"kill -{signal} {pid}")
        output = await tool.ainvoke({"command": command})

        return RunbookResult(
            success=True,
            message=f"Сигнал {signal} отправлен процессу {pid}",
            details=output,
        )
