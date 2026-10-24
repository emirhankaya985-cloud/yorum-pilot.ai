"""Network-less regression tests for message providers, cleanup, and config guards."""
import asyncio
import httpx
import pytest

from app.notifications import (
    telegram_send, ntfy_send, NotificationDeliveryError,
)
from app.config import get_settings
from app.maintenance import cleanup_once
from app.models import Review


BOT = '123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ12345'
CHAT = '1234567'
TOPIC = 'topic-yorumpilot-tests-9911011'


def async_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize('status, body', [
    (429, {'ok': False}), (200, {'ok': False}), (503, {'ok': False}),
])
def test_telegram_failure_modes_are_not_success(status, body):
    async def scenario():
        async with async_client(lambda request: httpx.Response(status, json=body)) as client:
            with pytest.raises(NotificationDeliveryError):
                await telegram_send(BOT, CHAT, 'Synthetic demo only', client=client)
    asyncio.run(scenario())


def test_telegram_malformed_json_fails_closed():
    async def scenario():
        async with async_client(lambda request: httpx.Response(200, text='not JSON')) as client:
            with pytest.raises(NotificationDeliveryError):
                await telegram_send(BOT, CHAT, 'Synthetic demo only', client=client)
    asyncio.run(scenario())


def test_ntfy_non_success_response_not_accepted():
    async def scenario():
        async with async_client(lambda request: httpx.Response(500, text='fail')) as client:
            with pytest.raises(NotificationDeliveryError):
                await ntfy_send(TOPIC, 'Synthetic demo only', client=client)
    asyncio.run(scenario())


def test_ntfy_topic_and_body_validation_before_network():
    async def scenario():
        async with async_client(lambda request: pytest.fail('unexpected network request')) as client:
            with pytest.raises(ValueError):
                await ntfy_send('https://evil.example/', 'test', client=client)
            with pytest.raises(ValueError):
                await ntfy_send(TOPIC, '', client=client)
    asyncio.run(scenario())


def test_google_mode_never_enables_live_publish(monkeypatch):
    monkeypatch.setenv('GOOGLE_MODE', 'live')
    with pytest.raises(RuntimeError, match='not enabled'):
        get_settings()


def test_cleanup_uses_session_factory(monkeypatch, client):
    # Existing test fixture supplies a separate database, never touches production Neon.
    monkeypatch.setattr('app.maintenance.SessionLocal', client.db_factory)
    assert cleanup_once() == 0
