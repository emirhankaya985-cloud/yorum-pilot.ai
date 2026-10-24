"""Optional network transport adapters; deliberately not connected to customer events yet.

No secrets, reviewer details or customer-auth tokens are accepted in the message body.
"""
import re
import httpx


class NotificationDeliveryError(Exception):
    pass


def _validate_summary(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 400:
        raise ValueError('Notification summary length must be 1..400')
    return value


async def telegram_send(bot_token: str, chat_id: str, summary: str, *, client: httpx.AsyncClient | None = None):
    """Transport only. Caller must verify per-tenant recipient ownership beforehand."""
    if not re.fullmatch(r'[0-9]{6,15}:[A-Za-z0-9_-]{25,80}', bot_token):
        raise ValueError('Invalid Telegram token format')
    if not re.fullmatch(r'-?[0-9]{3,20}', chat_id):
        raise ValueError('Invalid Telegram chat ID')
    body = {'chat_id': chat_id, 'text': _validate_summary(summary), 'disable_web_page_preview': True}
    owned = client is None
    client = client or httpx.AsyncClient(timeout=8)
    try:
        r=await client.post(f'https://api.telegram.org/bot{bot_token}/sendMessage',json=body)
        if r.status_code>=400 or not r.json().get('ok', False):
            raise NotificationDeliveryError('Telegram delivery failed')
    except (httpx.HTTPError, ValueError) as exc:
        raise NotificationDeliveryError('Telegram delivery failed') from None
    finally:
        if owned:
            await client.aclose()


async def ntfy_send(topic: str, summary: str, *, client: httpx.AsyncClient | None = None):
    """Fixed ntfy.sh host prevents user-supplied webhook SSRF."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,90}', topic):
        raise ValueError('Topic requires a nontrivial random identifier')
    owned = client is None
    client = client or httpx.AsyncClient(timeout=8)
    try:
        r=await client.post(f'https://ntfy.sh/{topic}',content=_validate_summary(summary).encode(),
                            headers={'Title':'YorumPilot AI','Priority':'default'})
        if r.status_code>=400:
            raise NotificationDeliveryError('ntfy delivery failed')
    except httpx.HTTPError:
        raise NotificationDeliveryError('ntfy delivery failed') from None
    finally:
        if owned:
            await client.aclose()
