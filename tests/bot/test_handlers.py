"""Tests for notify_incident message formatting and /start handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers import SEVERITY_EMOJI, notify_incident


class TestNotifyIncident:
    @pytest.fixture
    def mock_bot(self):
        bot = AsyncMock()
        msg = MagicMock()
        msg.message_id = 42
        bot.send_message = AsyncMock(return_value=msg)
        return bot

    @pytest.fixture
    def sample_interrupt_data(self):
        return {
            "host": "web-01.example.com",
            "incident": {
                "db_id": 1,
                "severity": "critical",
                "problem_type": "disk_full",
                "evidence": "/ заполнен на 95%",
                "dangerous_actions": [
                    {"label": "Очистить логи", "runbook": "clear_old_logs", "params": {"path": "/var/log"}},
                ],
            },
            "host_config": {"host": "web-01.example.com", "ssh_user": "deploy"},
        }

    @patch("app.db.session.get_session")
    async def test_send_message_called_with_correct_chat(
        self, mock_session, mock_bot, sample_interrupt_data
    ):
        mock_session.return_value.__aenter__ = AsyncMock()
        mock_session.return_value.__aexit__ = AsyncMock()

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args
        assert call_kwargs.kwargs["chat_id"] == 123456

    @patch("app.db.session.get_session")
    async def test_message_contains_host_and_problem_type(
        self, mock_session, mock_bot, sample_interrupt_data
    ):
        mock_session.return_value.__aenter__ = AsyncMock()
        mock_session.return_value.__aexit__ = AsyncMock()

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "web-01.example.com" in text
        assert "disk_full" in text

    @patch("app.db.session.get_session")
    async def test_message_contains_severity_emoji(
        self, mock_session, mock_bot, sample_interrupt_data
    ):
        mock_session.return_value.__aenter__ = AsyncMock()
        mock_session.return_value.__aexit__ = AsyncMock()

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert SEVERITY_EMOJI["critical"] in text

    @patch("app.db.session.get_session")
    async def test_message_contains_evidence(
        self, mock_session, mock_bot, sample_interrupt_data
    ):
        mock_session.return_value.__aenter__ = AsyncMock()
        mock_session.return_value.__aexit__ = AsyncMock()

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "/ заполнен на 95%" in text

    @patch("app.db.session.get_session")
    async def test_message_has_keyboard_when_db_id(
        self, mock_session, mock_bot, sample_interrupt_data
    ):
        mock_session.return_value.__aenter__ = AsyncMock()
        mock_session.return_value.__aexit__ = AsyncMock()

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs.get("reply_markup") is not None

    async def test_no_keyboard_without_db_id(self, mock_bot):
        """Without db_id, notification is sent without buttons."""
        data = {
            "host": "web-01",
            "incident": {
                "severity": "info",
                "problem_type": "test",
                "evidence": "test",
                "dangerous_actions": [],
            },
        }
        await notify_incident(mock_bot, 123456, "thread-1", data)

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert "reply_markup" not in call_kwargs

    @patch("app.db.session.get_session")
    async def test_warning_severity_emoji(self, mock_session, mock_bot):
        mock_session.return_value.__aenter__ = AsyncMock()
        mock_session.return_value.__aexit__ = AsyncMock()

        interrupt_data = {
            "host": "db-01",
            "incident": {
                "db_id": 2,
                "severity": "warning",
                "problem_type": "replication_lag",
                "evidence": "Отставание 60s",
                "dangerous_actions": [],
            },
        }

        await notify_incident(mock_bot, 123456, "thread-2", interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert SEVERITY_EMOJI["warning"] in text
