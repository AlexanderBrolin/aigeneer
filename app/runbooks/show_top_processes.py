"""Runbook: show top CPU/memory consuming processes via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class ShowTopProcessesRunbook(Runbook):
    """Show top processes sorted by CPU usage.

    Read-only runbook. Tools are pre-bound to the target host.

    Params:
        count: Number of processes to show (default 20).
    """

    name = "show_top_processes"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        count = params.get("count", 20)
        # ps output: header line + count process lines
        command = f"ps aux --sort=-%cpu | head -n {count + 1}"

        output = await tool.ainvoke({"command": command})

        return RunbookResult(
            success=True,
            message=f"Топ {count} процессов по загрузке CPU",
            details=output,
        )
