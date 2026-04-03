"""Runbook: show disk usage by directory via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class ShowDiskUsageRunbook(Runbook):
    """Show top disk-consuming directories using du.

    Read-only runbook. Tools are pre-bound to the target host.

    Params:
        path: Root path to scan (default "/").
        count: Number of top entries to show (default 20).
    """

    name = "show_disk_usage"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")

        path = params.get("path", "/")
        count = params.get("count", 20)
        command = f"du -sh {path}/* 2>/dev/null | sort -rh | head -n {count}"

        output = await tool.ainvoke({"command": command})

        return RunbookResult(
            success=True,
            message=f"Топ {count} директорий по объёму в {path}",
            details=output,
        )
