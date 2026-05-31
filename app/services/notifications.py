"""
Expo Push Notification service.

Delivers push notifications via the Expo managed push service:
  https://docs.expo.dev/push-notifications/sending-notifications/

The server side is a plain HTTPS POST to Expo's REST endpoint — no SDK needed.
Mobile clients obtain an ExponentPushToken and POST it to
  PATCH /api/v1/users/me/push-token
which stores it on UserProfile.push_token for use here.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_push(
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
    *,
    sound: str = "default",
) -> bool:
    """
    Send a single push notification via Expo Push API.

    Returns True if Expo accepted the message, False on any error.
    Never raises — all failures are logged and swallowed so the caller
    (autopilot scanner) is never interrupted by a notification failure.
    """
    if not token or not token.startswith("ExponentPushToken["):
        logger.debug("Skipping push — no valid Expo token: %.30r", token)
        return False

    payload: dict = {
        "to": token,
        "title": title,
        "body": body,
        "sound": sound,
        "data": data or {},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_EXPO_PUSH_URL, json=payload)
            resp.raise_for_status()
            tickets = resp.json().get("data") or [{}]
            ticket = tickets[0] if isinstance(tickets, list) else {}
            if ticket.get("status") == "error":
                logger.warning("Expo push rejected: %s", ticket.get("details"))
                return False
            logger.info("Push sent → %.25s…: %r", token, title)
            return True
    except Exception as exc:
        logger.warning("Push notification failed (%s): %s", type(exc).__name__, exc)
        return False
