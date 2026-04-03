"""Tests for CheckBackupRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.check_backup import CheckBackupRunbook


BACKUP_FILES_OUTPUT = """\
/backups/mysql/db_2026-04-03_02-00.sql.gz
/backups/mysql/db_2026-04-03_03-00.sql.gz
/backups/mysql/db_2026-04-03_04-00.sql.gz
"""


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestCheckBackupRunbook:
    """Tests for CheckBackupRunbook."""

    def _make_runbook(self, response: str) -> CheckBackupRunbook:
        tool = MockTool("ssh_exec", response)
        return CheckBackupRunbook(tools=[tool])

    async def test_missing_backup_path_returns_failure(self):
        """backup_path is REQUIRED — returns failure if missing."""
        runbook = self._make_runbook(BACKUP_FILES_OUTPUT)
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "backup_path" in result.message.lower() or "backup" in result.message.lower()

    async def test_files_found_returns_success(self):
        runbook = self._make_runbook(BACKUP_FILES_OUTPUT)
        result = await runbook.execute({"backup_path": "/backups/mysql"})
        assert isinstance(result, RunbookResult)
        assert result.success is True

    async def test_files_found_message_contains_count(self):
        runbook = self._make_runbook(BACKUP_FILES_OUTPUT)
        result = await runbook.execute({"backup_path": "/backups/mysql"})
        assert "3" in result.message

    async def test_files_found_details_contains_output(self):
        runbook = self._make_runbook(BACKUP_FILES_OUTPUT)
        result = await runbook.execute({"backup_path": "/backups/mysql"})
        assert BACKUP_FILES_OUTPUT in result.details

    async def test_no_files_returns_failure(self):
        """Empty output means no recent backups."""
        runbook = self._make_runbook("")
        result = await runbook.execute({"backup_path": "/backups/mysql"})
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "No recent backups" in result.message or "бекап" in result.message.lower() or "backup" in result.message.lower()

    async def test_no_files_message(self):
        runbook = self._make_runbook("")
        result = await runbook.execute({"backup_path": "/backups/mysql"})
        assert result.success is False

    async def test_backup_path_used_in_command(self):
        """backup_path parameter is inserted into the find command."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return BACKUP_FILES_OUTPUT

        runbook = CheckBackupRunbook(tools=[CaptureTool()])
        await runbook.execute({"backup_path": "/backups/custom"})
        assert "/backups/custom" in called_with["command"]

    async def test_is_not_dangerous(self):
        runbook = self._make_runbook(BACKUP_FILES_OUTPUT)
        assert runbook.is_dangerous is False

    async def test_name(self):
        runbook = self._make_runbook(BACKUP_FILES_OUTPUT)
        assert runbook.name == "check_backup"
