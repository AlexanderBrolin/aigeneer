"""Runbook: free OS page cache and dentries/inodes via SSH."""

from app.runbooks.base import Runbook, RunbookResult


class FreeMemoryRunbook(Runbook):
    """Drop OS page cache, dentries and inodes on a remote host.

    Runs: sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'
    This is safe to run on a live system but affects performance briefly.
    Tools are pre-bound to the target host — no host params needed.

    No required params.
    """

    name = "free_memory"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")
        command = "sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'"
        output = await tool.ainvoke({"command": command})

        return RunbookResult(
            success=True,
            message="Кэш памяти (page cache, dentries, inodes) очищен",
            details=output,
        )
