"""Telegram BotFather flow: fully offline mock API tests; no real bot/token used."""
import hashlib
import hmac
from urllib.parse import urlparse, parse_qs

import pytest
from app.models import TelegramBinding, Review, TelegramUpdate
from app import telegram_bot as bot
from .conftest import signup, csrf


TOKEN = '123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ12345'


def activate(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setattr(bot, '_bot_username', 'YorumPilotAI_Bot')
    messages = []

    async def no_network_api(method, payload):
        messages.append((method, payload))
        return {'ok': True}

    monkeypatch.setattr(bot, '_api', no_network_api)
    return messages


def signed_headers():
    return {'X-Telegram-Bot-Api-Secret-Token': bot._webhook_secret()}


def link(client, org, messages, *, update_id=100, chat_id=1234567):
    response = client.post(f'/api/organizations/{org}/telegram/pair', headers=csrf(client))
    assert response.status_code == 200, response.text
    url = response.json()['deep_link']
    assert url.startswith('https://t.me/YorumPilotAI_Bot?start=')
    token = parse_qs(urlparse(url).query)['start'][0]
    assert len(token) > 20
    data = {'update_id': update_id, 'message': {
        'chat': {'id':chat_id,'type':'private'},
        'from':{'id':chat_id},
        'text':'/start '+token}}
    res = client.post('/api/telegram/webhook', headers=signed_headers(), json=data)
    assert res.status_code == 200, res.text
    assert any(name=='sendMessage' for name,_ in messages)
    return data


def test_unconfigured_bot_has_no_pairing(client, monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    org = signup(client)
    status = client.get(f'/api/organizations/{org}/telegram/status')
    assert status.status_code == 200
    assert not status.json()['bot_configured']
    pair = client.post(f'/api/organizations/{org}/telegram/pair', headers=csrf(client))
    assert pair.status_code == 503
    webhook = client.post('/api/telegram/webhook', json={'update_id':5})
    assert webhook.status_code == 503


def test_webhook_rejects_spoofed_or_oversized_updates(client, monkeypatch):
    activate(monkeypatch)
    assert client.post('/api/telegram/webhook',json={'update_id':1}).status_code == 403
    assert client.post('/api/telegram/webhook',headers=signed_headers(),data=b'x'*12001).status_code == 413
    assert client.post('/api/telegram/webhook',headers=signed_headers(),data=b'invalid-json').status_code == 400


def test_start_link_is_single_use_and_update_is_idempotent(client, monkeypatch):
    messages=activate(monkeypatch)
    org=signup(client)
    data=link(client,org,messages)
    with client.db_factory() as db:
        binding=db.get(TelegramBinding,org)
        assert binding and binding.chat_id=='1234567'
        assert db.get(TelegramUpdate,100)
    prev=len(messages)
    again=client.post('/api/telegram/webhook',headers=signed_headers(),json=data)
    assert again.status_code==200 and again.json()['duplicate']
    assert len(messages)==prev
    data['update_id']=101
    reused=client.post('/api/telegram/webhook',headers=signed_headers(),json=data)
    assert reused.status_code==200
    assert 'geçersiz' in messages[-1][1]['text']


def test_demo_alert_buttons_and_owner_only_actions(client, monkeypatch):
    messages=activate(monkeypatch)
    org=signup(client)
    link(client,org,messages)
    reviews=client.get(f'/api/organizations/{org}/reviews').json()
    review_id=reviews[0]['id']
    notify=client.post(f'/api/organizations/{org}/telegram/test',headers=csrf(client))
    assert notify.status_code == 200, notify.text
    assert notify.json()['real_google_publish'] is False
    payload=messages[-1][1]
    assert payload['chat_id']=='1234567'
    assert 'DEMO' in payload['text']
    assert payload['reply_markup']['inline_keyboard'][0][0]['callback_data'].startswith('v1:a:')

    def press(uid,action,sender=1234567):
        return client.post('/api/telegram/webhook',headers=signed_headers(),json={
            'update_id':uid,'callback_query':{'id':str(uid),'data':f'v1:{action}:{review_id}',
            'from':{'id':sender},'message':{'chat':{'type':'private','id':1234567}}}})

    assert press(201,'a',sender=999).status_code==200
    with client.db_factory() as db:
        assert db.get(Review,review_id).status=='awaiting_approval'

    assert press(202,'h').status_code==200
    with client.db_factory() as db:
        assert db.get(Review,review_id).status=='deferred'

    assert press(203,'a').status_code==200
    with client.db_factory() as db:
        rv=db.get(Review,review_id)
        assert rv.status=='approved'
        assert rv.draft.approved_by is not None
    assert press(204,'r').status_code==200
    with client.db_factory() as db:
        rv=db.get(Review,review_id)
        assert rv.status=='rejected'
        assert rv.draft.approved_by is None
    assert all(name!='publishGoogle' for name,_ in messages)
    assert any(name=='answerCallbackQuery' for name,_ in messages)


def test_private_only_and_disconnection(client, monkeypatch):
    messages=activate(monkeypatch)
    org=signup(client)
    data=link(client,org,messages)
    assert client.post(f'/api/organizations/{org}/telegram/disconnect',headers=csrf(client)).status_code==200
    assert not client.get(f'/api/organizations/{org}/telegram/status').json()['linked']
    data['update_id']=401
    data['message']['chat']={'id':-10000000,'type':'supergroup'}
    prev=len(messages)
    assert client.post('/api/telegram/webhook',headers=signed_headers(),json=data).status_code==200
    assert len(messages)==prev


def test_cross_tenant_pairing_not_authorized(client, monkeypatch):
    activate(monkeypatch)
    first=signup(client)
    client.cookies.clear()
    second=signup(client,'other@example.com','Other')
    assert client.get(f'/api/organizations/{first}/telegram/status').status_code==404
    assert client.post(f'/api/organizations/{first}/telegram/pair',headers=csrf(client)).status_code==404
    assert client.get(f'/api/organizations/{second}/telegram/status').status_code==200
