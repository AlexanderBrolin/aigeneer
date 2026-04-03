"""Runbook: show active network connections via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class ShowConnectionsRunbook(Runbook):
    """Show active network connections using ss.

    Read-only runbook. Tools are pre-bound to the target host.

    Params:
        count: Number of connections to show (default 50).
    """

    name = "show_connections"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        count = params.get("count", 50)
        # ss output: header line + count connection lines
        command = f"ss -tunp | head -n {count + 1}"

        output = await tool.ainvoke({"command": command})

        return RunbookResult(
            success=True,
            message=f"Активные сетевые соединения (до {count})",
            details=output,
        )
