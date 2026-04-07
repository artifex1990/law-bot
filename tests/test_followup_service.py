"""Tests: FollowupService logic."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from src.services.followup_service import FollowupService


@pytest.fixture
def followup_svc(mock_messenger):
    with patch("src.services.followup_service.settings") as cfg:
        cfg.FOLLOWUP_ENABLED = True
        cfg.FOLLOWUP_CHECK_INTERVAL_MIN = 1
        cfg.FOLLOWUP_INTERVALS_HOURS = [1, 12, 24, 72]
        cfg.FOLLOWUP_MESSAGES = [
            "Msg 1h",
            "Msg 12h",
            "Msg 24h",
            "Msg 72h",
        ]
        return FollowupService(mock_messenger)


def test_pick_reminder_first(followup_svc):
    since = timedelta(hours=2)
    idx = followup_svc._pick_reminder_index(since, 0)
    assert idx == 0


def test_pick_reminder_second(followup_svc):
    since = timedelta(hours=13)
    idx = followup_svc._pick_reminder_index(since, 1)
    assert idx == 1


def test_pick_reminder_third(followup_svc):
    since = timedelta(hours=25)
    idx = followup_svc._pick_reminder_index(since, 2)
    assert idx == 2


def test_pick_reminder_none_already_sent(followup_svc):
    since = timedelta(hours=2)
    idx = followup_svc._pick_reminder_index(since, 4)
    assert idx is None


def test_pick_reminder_none_too_early(followup_svc):
    since = timedelta(minutes=30)
    idx = followup_svc._pick_reminder_index(since, 0)
    assert idx is None


def test_should_complete_after_max(followup_svc):
    since = timedelta(hours=73)
    assert followup_svc._should_complete(since) is True


def test_should_not_complete_within(followup_svc):
    since = timedelta(hours=50)
    assert followup_svc._should_complete(since) is False


def test_get_message(followup_svc):
    assert followup_svc._get_message(0) == "Msg 1h"
    assert followup_svc._get_message(3) == "Msg 72h"
    assert followup_svc._get_message(99) == "Msg 72h"


@pytest.mark.asyncio
async def test_send_reminder(followup_svc, mock_messenger):
    await followup_svc._send_reminder("123", "Hi!")
    mock_messenger.send_message.assert_called_once()
    sent = mock_messenger.send_message.call_args[0][0]
    assert sent.content == "Hi!"
    assert sent.chat_id == "123"
