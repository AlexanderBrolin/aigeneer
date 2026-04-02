"""Tests for incident_keyboard and callback data format."""

from __future__ import annotations

from app.bot.callbacks import incident_keyboard


class TestIncidentKeyboard:
    def test_generates_correct_buttons_for_dangerous_actions(self):
        incident = {
            "dangerous_actions": [
                {"label": "Рестарт Apache", "runbook": "restart_service", "params": {"service": "apache2"}},
                {"label": "Очистить логи", "runbook": "clear_old_logs", "params": {"path": "/var/log"}},
            ],
        }
        markup = incident_keyboard("thread-123", incident)
        rows = markup.inline_keyboard

        # 2 action buttons + 1 ignore button = 3 rows (adjust(1) means 1 per row)
        assert len(rows) == 3

        # First action
        assert rows[0][0].text == "Рестарт Apache"
        assert rows[0][0].callback_data == "action:thread-123:0"

        # Second action
        assert rows[1][0].text == "Очистить логи"
        assert rows[1][0].callback_data == "action:thread-123:1"

        # Ignore button always last
        assert rows[2][0].text == "Игнорировать"
        assert rows[2][0].callback_data == "ignore:thread-123"

    def test_ignore_button_present_when_no_dangerous_actions(self):
        incident = {"dangerous_actions": []}
        markup = incident_keyboard("thread-456", incident)
        rows = markup.inline_keyboard

        assert len(rows) == 1
        assert rows[0][0].text == "Игнорировать"
        assert rows[0][0].callback_data == "ignore:thread-456"

    def test_keyboard_with_missing_dangerous_actions_key(self):
        incident = {}
        markup = incident_keyboard("thread-789", incident)
        rows = markup.inline_keyboard

        assert len(rows) == 1
        assert rows[0][0].text == "Игнорировать"

    def test_callback_data_format_action(self):
        incident = {
            "dangerous_actions": [
                {"label": "Test", "runbook": "restart_service", "params": {}},
            ],
        }
        markup = incident_keyboard("abc-def", incident)
        action_btn = markup.inline_keyboard[0][0]

        parts = action_btn.callback_data.split(":")
        assert parts[0] == "action"
        assert parts[1] == "abc-def"
        assert parts[2] == "0"

    def test_callback_data_format_ignore(self):
        incident = {"dangerous_actions": []}
        markup = incident_keyboard("abc-def", incident)
        ignore_btn = markup.inline_keyboard[0][0]

        parts = ignore_btn.callback_data.split(":")
        assert parts[0] == "ignore"
        assert parts[1] == "abc-def"

    def test_one_button_per_row(self):
        incident = {
            "dangerous_actions": [
                {"label": f"Action {i}", "runbook": "restart_service", "params": {}}
                for i in range(5)
            ],
        }
        markup = incident_keyboard("thread-x", incident)
        rows = markup.inline_keyboard

        # 5 actions + 1 ignore = 6 rows
        assert len(rows) == 6
        for row in rows:
            assert len(row) == 1
