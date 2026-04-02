"""Tests for notify_incident message formatting and /start handler."""

from __future__ import annotations

import json
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
                "severity": "critical",
                "problem_type": "disk_full",
                "evidence": "/ заполнен на 95%",
                "dangerous_actions": [
                    {"label": "Очистить логи", "runbook": "clear_old_logs", "params": {"path": "/var/log"}},
                ],
            },
        }

    @patch("app.bot.handlers._get_redis")
    async def test_send_message_called_with_correct_chat(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args
        assert call_kwargs.kwargs["chat_id"] == 123456

    @patch("app.bot.handlers._get_redis")
    async def test_message_contains_host_and_problem_type(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "web-01.example.com" in text
        assert "disk_full" in text

    @patch("app.bot.handlers._get_redis")
    async def test_message_contains_severity_emoji(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert SEVERITY_EMOJI["critical"] in text

    @patch("app.bot.handlers._get_redis")
    async def test_message_contains_evidence(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "/ заполнен на 95%" in text

    @patch("app.bot.handlers._get_redis")
    async def test_message_has_keyboard(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["reply_markup"] is not None

    @patch("app.bot.handlers._get_redis")
    async def test_stores_data_in_redis(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        # Key is tg_thread:{message_id}
        assert call_args.args[0] == "tg_thread:42"
        # TTL = 3600
        assert call_args.args[1] == 3600
        # Value is JSON containing thread_id and incident
        stored = json.loads(call_args.args[2])
        assert stored["thread_id"] == "thread-1"
        assert stored["incident"]["problem_type"] == "disk_full"

    @patch("app.bot.handlers._get_redis")
    async def test_redis_connection_closed(
        self, mock_get_redis, mock_bot, sample_interrupt_data
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await notify_incident(mock_bot, 123456, "thread-1", sample_interrupt_data)

        mock_redis.aclose.assert_called_once()

    @patch("app.bot.handlers._get_redis")
    async def test_warning_severity_emoji(
        self, mock_get_redis, mock_bot
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        interrupt_data = {
            "host": "db-01",
            "incident": {
                "severity": "warning",
                "problem_type": "replication_lag",
                "evidence": "Отставание 60s",
                "dangerous_actions": [],
            },
        }

        await notify_incident(mock_bot, 123456, "thread-2", interrupt_data)

        text = mock_bot.send_message.call_args.kwargs["text"]
        assert SEVERITY_EMOJI["warning"] in text
