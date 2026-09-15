"""Keep the Ontada grant alive so nobody has to sign in again.

Measured 2026-09-13 → 2026-09-14 against the live gateway:

* the access token lives **1799 s** (~30 min);
* the token response carries **no** refresh-token lifetime — no
  `refresh_expires_in`, nothing in the id_token — so there is no published
  number to plan against;
* `.well-known/smart-configuration` advertises `grant_types_supported:
  ["authorization_code"]` and does not list `refresh_token` at all, even though
  `permission-offline` is in its capabilities and `offline_access` is granted.

Refreshing lazily — only when a request arrives after expiry, which is what
`routers.ontada._token` did alone — left the grant idle overnight. The next
morning the first refresh came back `400 [invalid_grant]` and a person had to
repeat the browser login. This task refreshes on a timer instead, so the grant
is exercised every few minutes and never goes cold.

What this CANNOT do: remove the first login. The gateway has no
`client_credentials`, so the first token in a deployment always comes from a
human in a browser. What it removes is every re-login after that.

One process only. Behind replicas this would have every worker refreshing the
same row and racing on a rotated refresh token — elect one, or move the loop to
a scheduled job, before scaling out.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .. import config, db
from ..integrations import ontada

log = logging.getLogger("genesilico-ehr.token-keeper")

TOKEN_ID = "ontada-default"

_task: asyncio.Task | None = None

# One refresh at a time. The keeper's timer and a request arriving on the
# on-demand path can otherwise reach the token endpoint together, each holding
# the same refresh token — and because Ontada ROTATES on every renewal, the
# slower of the two presents one that has just been spent and is told
# `invalid_grant`. That looks identical to a dead grant and is not one.
_refresh_lock = asyncio.Lock()


def state(row: db.OAuthToken | None) -> dict:
    """The keeper's own bookkeeping, carried inside the token row's JSON so
    this needs no migration."""
    if row is None:
        return {}
    return dict((row.raw or {}).get("keeper") or {})


def _remember(row: db.OAuthToken, **fields) -> None:
    # The JSON column is a plain dict, not a MutableDict: SQLAlchemy only sees
    # the change if the attribute is reassigned.
    raw = dict(row.raw or {})
    raw["keeper"] = {**(raw.get("keeper") or {}), **fields}
    row.raw = raw


def due(row: db.OAuthToken) -> bool:
    """True when the access token is inside the refresh window.

    Deliberately early: renewing at T-10 min on a 30-minute token means a
    transient failure still has ~10 minutes of working token to retry inside,
    instead of surfacing to a user as a 502.
    """
    remaining = (db.as_aware(row.expires_at) - db.utcnow()).total_seconds()
    return remaining <= config.ONTADA_REFRESH_SKEW_SECONDS


def token_of(row: db.OAuthToken) -> dict:
    """The row as the shape `integrations.ontada` expects."""
    return {
        "access_token": row.access_token,
        "refresh_token": row.refresh_token,
        "patient": row.patient_id,
        "fhir_base": row.fhir_base,
        "expires_at": db.as_aware(row.expires_at).timestamp(),
        **{k: v for k, v in (row.raw or {}).items() if k != "keeper"},
    }


def reauth_required(row: db.OAuthToken | None) -> bool:
    """Whether a person really must sign in again.

    The stored flag alone is not enough: a live access token beats it every
    time. Anything else means one bad refresh can leave a working connection
    permanently labelled broken.
    """
    if row is None:
        return False
    if db.as_aware(row.expires_at) > db.utcnow():
        return False
    return bool(state(row).get("reauth_required"))


async def refresh_and_store(session: AsyncSession, row: db.OAuthToken,
                            *, reason: str) -> dict:
    """Refresh, persist, and record what happened. Returns the live token dict.

    Serialised against every other refresh in this process. Raises whatever
    `ontada.refresh` raised, after marking the row, so callers can turn it into
    their own error shape.
    """
    async with _refresh_lock:
        # Re-read after taking the lock: whoever held it may have just renewed,
        # in which case our refresh token is already spent and the stored one is
        # good. A forced manual refresh still goes ahead — proving the grant
        # works is the whole point of that endpoint.
        await session.refresh(row)
        if reason != "manual" and not due(row):
            log.info("ontada refresh skipped (%s): renewed by another path", reason)
            return token_of(row)

        tok = token_of(row)
        try:
            new = await ontada.refresh(tok)
        except Exception as exc:
            text = str(exc)
            await session.refresh(row)
            # A spent refresh token and a revoked one are the same message. The
            # row settles it: if what is stored now works, we simply lost a race
            # and nothing is wrong. Latching reauth_required here would send
            # someone to sign in again for no reason.
            if "invalid_grant" in text and not due(row):
                log.info("ontada refresh raced (%s); the stored token is live to %s",
                         reason, row.expires_at)
                return token_of(row)
            # Otherwise invalid_grant is terminal: the authorization server has
            # thrown the refresh token away, and retrying on a timer only burns
            # requests. Say so on the row so the UI can ask for one login
            # instead of failing every read with a 502.
            _remember(row,
                      last_error=text,
                      last_error_at=db.utcnow().isoformat(),
                      reauth_required="invalid_grant" in text,
                      failures=int(state(row).get("failures", 0)) + 1)
            await session.commit()
            log.warning("ontada refresh failed (%s): %s", reason, text)
            raise

        row.access_token = new["access_token"]
        # Ontada rotates the refresh token. Keeping the old one after a rotation
        # is the classic way to break the next refresh.
        row.refresh_token = new.get("refresh_token") or row.refresh_token
        row.expires_at = db.from_epoch(new["expires_at"])
        if new.get("scope"):
            row.scope = new["scope"]
        rotated = bool(new.get("refresh_token")) and new.get("refresh_token") != tok["refresh_token"]
        _remember(row,
                  last_refresh_at=db.utcnow().isoformat(),
                  last_refresh_reason=reason,
                  rotated=rotated,
                  reauth_required=False,
                  last_error=None,
                  failures=0,
                  refreshes=int(state(row).get("refreshes", 0)) + 1)
        await session.commit()
        log.info("ontada token refreshed (%s); expires %s; refresh token %s",
                 reason, row.expires_at, "rotated" if rotated else "reused")
        return new


async def _tick() -> None:
    async with db.SessionLocal() as session:
        row = await session.get(db.OAuthToken, TOKEN_ID)
        if row is None or not row.refresh_token:
            return                      # nobody has logged in yet; nothing to keep
        if state(row).get("reauth_required"):
            return                      # the grant is gone; only a browser login fixes it
        if not due(row):
            return
        try:
            await refresh_and_store(session, row, reason="keepalive")
        except Exception:
            pass                        # already logged and recorded on the row


async def _loop(interval: int) -> None:
    log.info("ontada token keeper started: every %ss, renewing at T-%ss",
             interval, config.ONTADA_REFRESH_SKEW_SECONDS)
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A keeper that dies silently is worse than one that logs and
            # carries on — the failure would only show up as an expired token
            # hours later.
            log.exception("ontada token keeper tick failed")
        await asyncio.sleep(interval)


def start() -> None:
    global _task
    if not config.ONTADA_KEEPALIVE_SECONDS or _task is not None:
        return
    _task = asyncio.create_task(_loop(config.ONTADA_KEEPALIVE_SECONDS))


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
