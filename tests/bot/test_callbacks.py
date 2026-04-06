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
        markup = incident_keyboard(99, "thread-123", incident)
        rows = markup.inline_keyboard

        # 2 action + 1 resolve + 1 ignore = 4 rows
        assert len(rows) == 4

        # First action — uses incident DB ID
        assert rows[0][0].text == "Рестарт Apache"
        assert rows[0][0].callback_data == "act:99:0"

        # Second action
        assert rows[1][0].text == "Очистить логи"
        assert rows[1][0].callback_data == "act:99:1"

        # Resolve button
        assert rows[2][0].text == "Resolved"
        assert rows[2][0].callback_data == "resolve:99"

        # Ignore button
        assert rows[3][0].text == "Игнорировать"
        assert rows[3][0].callback_data == "ign:99"

    def test_ignore_button_present_when_no_dangerous_actions(self):
        incident = {"dangerous_actions": []}
        markup = incident_keyboard(5, "thread-456", incident)
        rows = markup.inline_keyboard

        # resolve + ignore = 2
        assert len(rows) == 2
        assert rows[0][0].text == "Resolved"
        assert rows[1][0].text == "Игнорировать"

    def test_keyboard_with_missing_dangerous_actions_key(self):
        incident = {}
        markup = incident_keyboard(7, "thread-789", incident)
        rows = markup.inline_keyboard
        assert len(rows) == 2  # resolve + ignore

    def test_callback_data_uses_incident_db_id(self):
        incident = {
            "dangerous_actions": [
                {"label": "Test", "runbook": "restart_service", "params": {}},
            ],
        }
        markup = incident_keyboard(42, "abc-def", incident)
        action_btn = markup.inline_keyboard[0][0]

        parts = action_btn.callback_data.split(":")
        assert parts[0] == "act"
        assert parts[1] == "42"  # incident DB ID
        assert parts[2] == "0"

    def test_one_button_per_row(self):
        incident = {
            "dangerous_actions": [
                {"label": f"Action {i}", "runbook": "restart_service", "params": {}}
                for i in range(3)
            ],
        }
        markup = incident_keyboard(10, "thread-x", incident)
        rows = markup.inline_keyboard

        # 3 actions + 1 resolve + 1 ignore = 5 rows
        assert len(rows) == 5
        for row in rows:
            assert len(row) == 1
