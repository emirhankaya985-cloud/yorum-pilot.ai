"""YorumPilot opt-in Telegram bot: signed webhook, private pairing and manual decisions.

A callback approves only a draft; it NEVER publishes anything to Google.
No bot token is exposed in logs, persisted records, or API responses.
"""
import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import identity, membership
from .config import get_settings
from .db import get_db
from .models import (Audit, Membership, Organization, Review, TelegramBinding,
                     TelegramPairing, TelegramUpdate, utcnow)
from .rate_limit import throttle

log = logging.getLogger(__name__)
router = APIRouter()
_bot_username = ''
BOT_URL = 'https://yorumpilot-api.onrender.com/api/telegram/webhook'
LINK_TTL_MINUTES = 10
MAX_UPDATE_BYTES = 12000


def _is_expired(value) -> bool:
    # SQLite test DB strips timezone metadata while Neon PostgreSQL retains it.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= utcnow()



def _token() -> str:
    return os.getenv('TELEGRAM_BOT_TOKEN', '').strip()


def _webhook_secret() -> str:
    return hmac.new(get_settings().secret_key.encode(), _token().encode(), hashlib.sha256).hexdigest()


class TelegramDeliveryError(Exception):
    pass


async def _api(method: str, payload: dict):
    token = _token()
    if not token:
        raise TelegramDeliveryError('Bot not configured')
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=4)) as client:
            response = await client.post(f'https://api.telegram.org/bot{token}/{method}', json=payload)
            response.raise_for_status()
            body = response.json()
            if not body.get('ok'):
                raise TelegramDeliveryError('Telegram rejected request')
            return body.get('result')
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise TelegramDeliveryError('Telegram transport failure') from None


async def configure_bot() -> None:
    """Run after deployment and token entry; intentionally nonfatal on network error."""
    global _bot_username
    if not _token():
        _bot_username = ''
        return
    if not re.fullmatch(r'[0-9]{6,15}:[A-Za-z0-9_-]{25,100}', _token()):
        log.error('TELEGRAM_BOT_TOKEN format invalid; webhook not configured')
        return
    try:
        bot = await _api('getMe', {})
        _bot_username = bot.get('username', '') if isinstance(bot, dict) else ''
        await _api('setWebhook', {
            'url': BOT_URL, 'secret_token': _webhook_secret(),
            'allowed_updates': ['message', 'callback_query'], 'max_connections': 2
        })
        await _api('setMyCommands', {'commands': [
            {'command': 'start', 'description': 'YorumPilot hesabını bağla'},
            {'command': 'status', 'description': 'Bağlantı durumunu kontrol et'},
            {'command': 'help', 'description': 'Kullanım ve güvenlik bilgileri'}
        ]})
        log.info('Telegram bot webhook registered (credentials omitted)')
    except TelegramDeliveryError:
        log.warning('Telegram registration failed; check Render environment and connectivity')


def _owner(request: Request, org_id: str, db: Session, *, write: bool = False):
    user = identity(request, db, write=write)
    membership(db, user, org_id, ('owner','admin'))
    return user


@router.get('/api/organizations/{org_id}/telegram/status')
def telegram_status(org_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(request, org_id, db)
    binding = db.get(TelegramBinding, org_id)
    return {
        'bot_configured': bool(_token()),
        'bot_username': _bot_username if _token() else '',
        'linked': bool(binding and binding.enabled),
        'mode': 'DEMO_ONLY',
        'real_google_publish': False
    }


@router.post('/api/organizations/{org_id}/telegram/pair')
def create_pair(org_id: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, org_id, db, write=True)
    throttle(request, 'telegram-pair', limit=6, seconds=300)
    if not _token() or not _bot_username:
        raise HTTPException(503, 'Telegram botu henüz Render üzerinden etkinleştirilmedi')
    code = secrets.token_urlsafe(18)
    digest = hashlib.sha256(code.encode('ascii')).hexdigest()
    pair = TelegramPairing(digest=digest, organization_id=org_id, user_id=user.id,
                           expires_at=utcnow() + timedelta(minutes=LINK_TTL_MINUTES))
    db.add(pair)
    db.commit()
    return {'deep_link': f'https://t.me/{_bot_username}?start={code}',
            'expires_minutes': LINK_TTL_MINUTES}


@router.post('/api/organizations/{org_id}/telegram/disconnect')
def disconnect(org_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(request, org_id, db, write=True)
    binding = db.get(TelegramBinding, org_id)
    if binding:
        db.delete(binding)
        db.commit()
    return {'linked': False}


def _buttons(review_id: str) -> dict:
    return {'inline_keyboard': [
        [{'text':'✅ Onayla', 'callback_data':f'v1:a:{review_id}'},
         {'text':'❌ Reddet', 'callback_data':f'v1:r:{review_id}'}],
        [{'text':'🕓 Beklet', 'callback_data':f'v1:h:{review_id}'}]
    ]}


@router.post('/api/organizations/{org_id}/telegram/test')
async def test_message(org_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(request, org_id, db, write=True)
    throttle(request, 'telegram-test', limit=6, seconds=300)
    if not _token():
        raise HTTPException(503, 'Telegram botu etkin değil')
    binding = db.get(TelegramBinding, org_id)
    if not binding or not binding.enabled:
        raise HTTPException(409, 'Önce Telegram sohbetini hesapla eşleştir')
    review = db.scalar(select(Review).where(Review.organization_id == org_id,
                Review.expires_at > utcnow(), Review.status.in_(['awaiting_approval','deferred']))
                .order_by(Review.created_at.desc()).limit(1))
    message = '🔔 YorumPilot AI — test bildirimi\n'
    keyboard = None
    if review:
        message += f'⭐ {review.stars}/5 · DEMO yorum\n{review.content[:300]}\n\n📝 Taslak: {review.draft.text[:350] if review.draft else "Yok"}\n\nGerçek Google yayını KAPALI.'
        keyboard = _buttons(review.id)
    else:
        message += 'Bağlantı başarılı. Şu anda onay bekleyen demo yorum yok. Gerçek Google yayını KAPALI.'
    try:
        body = {'chat_id': binding.chat_id, 'text': message, 'disable_web_page_preview': True}
        if keyboard:
            body['reply_markup'] = keyboard
        await _api('sendMessage', body)
    except TelegramDeliveryError:
        raise HTTPException(502, 'Telegram test bildirimi gönderilemedi') from None
    return {'sent': True, 'source':'DEMO_DATA', 'real_google_publish':False}


def _apply_action(db: Session, review_id: str, action: str, telegram_user_id: str, chat_id: str) -> str:
    review = db.get(Review, review_id)
    if not review or _is_expired(review.expires_at):
        return 'Yorum bulunamadı veya süresi doldu.'
    binding = db.get(TelegramBinding, review.organization_id)
    if not binding or not binding.enabled or binding.telegram_user_id != telegram_user_id or binding.chat_id != chat_id:
        return 'Bu işletme için işlem yetkin yok.'
    member = db.scalar(select(Membership).where(Membership.organization_id == review.organization_id,
                   Membership.user_id == binding.user_id, Membership.role.in_(['owner','admin'])))
    if not member:
        return 'İşletme yönetim yetkin bulunmuyor.'
    if not review.draft or review.draft.review_revision != review.revision:
        return 'Taslak güncelliğini kaybetti; panelden yenile.'
    if action == 'a' and review.status in ('awaiting_approval', 'deferred'):
        review.draft.approved_by = binding.user_id
        review.draft.approved_at = utcnow()
        review.status = 'approved'
        verb = 'telegram_approved'
        notice = '✅ Taslak ONAYLANDI. Google üzerinde paylaşılmadı.'
    elif action == 'r' and review.status in ('awaiting_approval', 'approved', 'deferred'):
        review.draft.approved_by = None
        review.draft.approved_at = None
        review.status = 'rejected'
        verb = 'telegram_rejected'
        notice = '❌ Taslak REDDEDİLDİ.'
    elif action == 'h' and review.status in ('awaiting_approval', 'deferred'):
        review.status = 'deferred'
        verb = 'telegram_deferred'
        notice = '🕓 Bekletildi; yorum panelde beklemeye alındı.'
    else:
        return 'Bu buton için işlem zaten tamamlanmış veya geçersiz.'
    db.add(Audit(organization_id=review.organization_id, user_id=binding.user_id,
                 action=verb, object_id=review.id))
    db.commit()
    return notice


async def _process_message(db: Session, message: dict):
    chat = message.get('chat') or {}
    sender = message.get('from') or {}
    if chat.get('type') != 'private' or not isinstance(sender.get('id'), int):
        return
    if str(chat.get('id')) != str(sender['id']):
        return
    chat_id = str(chat['id'])
    text = (message.get('text') or '').strip()
    reply = ''
    if text.startswith('/start '):
        code = text.split(' ',1)[1].strip()
        digest = hashlib.sha256(code.encode('utf-8')).hexdigest()
        pair = db.get(TelegramPairing, digest)
        if pair and pair.used_at is None and not _is_expired(pair.expires_at):
            member = db.scalar(select(Membership).where(
                Membership.organization_id == pair.organization_id,
                Membership.user_id == pair.user_id,
                Membership.role.in_(['owner','admin'])))
            if member:
                binding = db.get(TelegramBinding, pair.organization_id)
                if binding is None:
                    binding = TelegramBinding(organization_id=pair.organization_id,
                                user_id=pair.user_id,telegram_user_id=chat_id,chat_id=chat_id)
                    db.add(binding)
                else:
                    binding.user_id = pair.user_id
                    binding.telegram_user_id = chat_id
                    binding.chat_id = chat_id
                    binding.enabled = True
                pair.used_at = utcnow()
                db.commit()
                reply = '✅ YorumPilot hesabın bağlandı. Web panelinden test bildirimi gönderebilirsin. Google cevapları otomatik yayımlanmaz.'
        if not reply:
            reply = 'Bağlantı kodu geçersiz, kullanılmış veya süresi dolmuş. Web panelinden yeni kod oluştur.'
    elif text.startswith('/status'):
        linked = db.scalar(select(TelegramBinding).where(
            TelegramBinding.telegram_user_id == chat_id, TelegramBinding.enabled == True))
        reply = '✅ Bir YorumPilot hesabına bağlısın.' if linked else '⚪ Henüz bağlanmadın. Web panelindeki Ayarlar üzerinden bağlan.'
    else:
        reply = 'YorumPilot AI botuna hoş geldin!\nÖnce web paneli → Ayarlar → Telegram Bağla.\n/status - bağlantı durumu\n/help - yardım\n🔒 Gerçek Google yayını kapalı.'
    try:
        await _api('sendMessage', {'chat_id':chat_id,'text':reply})
    except TelegramDeliveryError:
        log.warning('Telegram private reply delivery failed')


async def _process_callback(db: Session, data: dict):
    sender = data.get('from') or {}
    msg = data.get('message') or {}
    chat = msg.get('chat') or {}
    callback_id = data.get('id','')
    value = data.get('data','')
    result = 'Geçersiz işlem.'
    if (isinstance(sender.get('id'),int) and chat.get('type') == 'private'
            and str(sender['id']) == str(chat.get('id')) and
            re.fullmatch(r'v1:[arh]:[0-9a-f]{32}', value)):
        _, action, review_id = value.split(':')
        result = _apply_action(db, review_id, action, str(sender['id']),str(chat['id']))
    if callback_id:
        try:
            await _api('answerCallbackQuery', {'callback_query_id': callback_id, 'text':result[:180],
                                                'show_alert':False})
        except TelegramDeliveryError:
            log.warning('Telegram callback response delivery failed')


@router.post('/api/telegram/webhook', include_in_schema=False)
async def webhook(request: Request, db: Session = Depends(get_db)):
    if not _token():
        raise HTTPException(503,'Bot not configured')
    supplied = request.headers.get('x-telegram-bot-api-secret-token','')
    if not hmac.compare_digest(supplied, _webhook_secret()):
        raise HTTPException(403,'Unauthorized webhook')
    raw = await request.body()
    if len(raw) > MAX_UPDATE_BYTES:
        raise HTTPException(413,'Update too large')
    try:
        import json
        update = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(400,'Bad JSON') from None
    if not isinstance(update,dict) or not isinstance(update.get('update_id'),int):
        raise HTTPException(400,'Invalid update')
    uid = update['update_id']
    if uid < 0 or uid > 2147483647:
        raise HTTPException(400,'Invalid update ID')
    if db.get(TelegramUpdate,uid):
        return {'ok':True,'duplicate':True}
    # Persist update ID before side effects to avoid duplicate button actions.
    db.add(TelegramUpdate(update_id=uid))
    db.commit()
    if isinstance(update.get('message'),dict):
        await _process_message(db, update['message'])
    elif isinstance(update.get('callback_query'),dict):
        await _process_callback(db, update['callback_query'])
    return {'ok':True}
