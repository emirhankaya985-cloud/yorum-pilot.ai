import asyncio
import pytest
import httpx
from app.google_oauth import new_pkce, sign_state, verify_state, OAuthStateError
from app.google import MockGoogleAdapter, PendingGoogleAdapter, GoogleIntegrationPending
from app.notifications import telegram_send, ntfy_send, NotificationDeliveryError


def test_pkce_state_tied_to_correct_identity():
    verifier,challenge=new_pkce()
    assert 43<=len(verifier)<=128 and 43<=len(challenge)<=128
    state=sign_state('owner-a','tenant-a','nonce-123')
    assert verify_state(state,'owner-a','tenant-a')=='nonce-123'
    with pytest.raises(OAuthStateError):
        verify_state(state,'owner-b','tenant-a')


def test_adapters_fail_closed():
    assert MockGoogleAdapter().publish_reply('demo-review','test').status=='simulated_published'
    with pytest.raises(GoogleIntegrationPending):
        PendingGoogleAdapter().publish_reply('accounts/1/locations/2/reviews/3','hello')


def test_notification_transports_mock_http():
    seen=[]
    def handler(request):
        seen.append((request.url.host, request.method))
        if request.url.host=='api.telegram.org':
            return httpx.Response(200,json={'ok':True})
        return httpx.Response(200,text='ok')
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await telegram_send('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ12345','1234567','Yeni demo yorum!',client=client)
            await ntfy_send('random-topic-abcdef12345','Yeni demo yorum!',client=client)
    asyncio.run(call())
    assert seen==[('api.telegram.org','POST'),('ntfy.sh','POST')]


def test_notification_bad_recipient_rejected():
    with pytest.raises(ValueError):
        asyncio.run(ntfy_send('public','Hello'))
    with pytest.raises(ValueError):
        asyncio.run(telegram_send('invalid','1234','Hello'))
