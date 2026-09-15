"""Ontada / iKnowMed SMART on FHIR.

Three facts drive the shape of this router, all verified against the live
gateway rather than assumed:

1. `.well-known/smart-configuration` advertises `authorization_code` and
   nothing else. There is no client_credentials grant, so a server cannot mint
   a token by itself — a human must sign in in a browser. Note the login page
   the server redirects to is a PROVIDER portal, not a patient one.

2. The registration now grants the full `user/*` read set plus
   `offline_access` — re-measured 2026-09-14, where the grant also widened to
   include `Binary.r`, `Basic.rs`, `Provenance.rs`, `MedicationDispense.rs` and
   `QuestionnaireResponse.rs`. It is still all-or-nothing: the server rejects
   the WHOLE request with [invalid_scope] if one element sits outside the
   registration, so there is no partial grant to fall back on.

3. The refresh token ROTATES on every renewal, and the token response carries
   no lifetime for it. `.well-known/smart-configuration` does not even list
   `refresh_token` in `grant_types_supported`, though it works. An idle grant
   dies: left unused for ~30 h it came back `400 [invalid_grant]` and needed a
   fresh browser login. services/token_keeper renews on a timer so the grant is
   never idle — see that module before changing anything about refresh here.

SCALING CAVEAT: the PKCE verifier is held in-process by integrations.ontada.
Behind more than one worker the callback can land on a process that never saw
the authorize call. Move `_PENDING` to Redis before running replicas.
"""
import base64
import json
import urllib.parse
import uuid

from fastapi import APIRouter, Depends
from fastapi import Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import cache, config, db
from ..errors import ApiError, Unconfigured, UpstreamError
from ..integrations import ontada
from ..services import clinical_summary, fhir_import, token_keeper

from .. import schemas as S

router = APIRouter(prefix="/ontada", tags=["ontada"])

TOKEN_ID = "ontada-default"


def _require_config() -> None:
    if not ontada.configured():
        raise Unconfigured(
            "Ontada FHIR",
            "Set ONTADA_CLIENT_ID and ONTADA_FHIR_BASE, plus either "
            "ONTADA_CLIENT_SECRET or a registered public key, in backend/.env",
        )


@router.get("/authorize", responses={200: {"model": S.OntadaAuthorize}, **S.ERRORS})
async def authorize():
    """Begin the SMART launch. The browser must open `authorize_url` — the
    gateway sits behind a WAF that rejects non-browser clients."""
    _require_config()
    try:
        return await ontada.authorize_url()
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc


@router.get("/callback")
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    session: AsyncSession = Depends(db.get_session),
):
    if error:
        detail = error_description or error
        return RedirectResponse(f"{config.FRONTEND_URL}/ehr/connect?ontada_error={detail}")
    if not code or not state:
        raise ApiError("Callback is missing `code` or `state`.", status=400)

    try:
        tok = await ontada.exchange_code(code, state)
    except Exception as exc:
        # Surface the server's own words verbatim. A token exchange fails for
        # reasons worth telling apart — invalid_client means the portal secret
        # and ONTADA_CLIENT_SECRET disagree; invalid_scope means the request
        # asked for something outside the grant — and a generic message would
        # send someone hunting in the wrong place.
        return RedirectResponse(f"{config.FRONTEND_URL}/ehr/connect?ontada_error={exc}")

    await _store_token(session, tok)
    return RedirectResponse(f"{config.FRONTEND_URL}/ehr/connect?ontada_connected=1")


async def _store_token(session: AsyncSession, tok: dict) -> db.OAuthToken:
    row = await session.get(db.OAuthToken, TOKEN_ID)
    if row is None:
        row = db.OAuthToken(id=TOKEN_ID)
        session.add(row)
    row.access_token = tok["access_token"]
    row.refresh_token = tok.get("refresh_token")
    row.expires_at = db.from_epoch(tok["expires_at"])
    row.scope = tok.get("scope", "")
    row.patient_id = tok.get("patient")
    row.fhir_base = tok.get("fhir_base", config.ONTADA_FHIR_BASE)
    # A fresh grant clears the keeper's failure state — including the
    # reauth_required flag that put the UI in this flow to begin with — but
    # keeps its running totals. How often this connection has had to be renewed,
    # and how often it has died, is the history that says whether a re-login is
    # a one-off or a pattern; overwriting `raw` wholesale threw it away.
    prior = token_keeper.state(row)
    raw = {k: v for k, v in tok.items() if k not in ("access_token", "refresh_token")}
    raw["keeper"] = {
        "refreshes": int(prior.get("refreshes", 0)),
        "logins": int(prior.get("logins", 0)) + 1,
        "last_login_at": db.utcnow().isoformat(),
        "reauth_required": False,
        "failures": 0,
        "last_error": None,
    }
    row.raw = raw
    await session.commit()
    return row


@router.post("/complete", responses={200: {"model": S.OntadaStatus}, **S.ERRORS})
async def complete(body: S.OntadaComplete, session: AsyncSession = Depends(db.get_session)):
    """Finish the login from the address the browser landed on.

    Ontada's registered redirect URI is a single-page app that strips the query
    string on load, so the code never reaches our callback by itself. This is
    the paste-it-back path, called by the UI so nobody has to open a terminal.

    The PKCE verifier lives in the backend process (integrations.ontada._PENDING,
    10-minute TTL), so the authorize call and this one must hit the same running
    backend, reasonably close together.
    """
    _require_config()
    code, state = body.code, body.state
    if body.url:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(body.url.strip()).query)
        if "error" in q:
            raise ApiError(
                f"Ontada refused the login: {q['error'][0]} — "
                f"{q.get('error_description', [''])[0]}",
                status=400, code="ontada_login_refused")
        code = code or q.get("code", [None])[0]
        state = state or q.get("state", [None])[0]
    if not code or not state:
        raise ApiError(
            "That address carries no ?code= and ?state=. Either the login did not "
            "finish, or the landing page dropped the query string before it could be "
            "copied — reopen the browser history entry for the redirect, which keeps "
            "the full address.",
            status=400, code="ontada_no_code")
    if not ontada.has_pending(state):
        # Not an upstream failure — the verifier that pairs with this code is
        # gone from this process (ten-minute TTL, single use, and it does not
        # survive a backend restart). Only starting again can fix it, so say
        # that rather than dressing it up as an Ontada outage.
        raise ApiError(
            "That login has lapsed — its one-time verifier is no longer held here "
            "(they last ten minutes, are single-use, and do not survive a backend "
            "restart). Press Connect to Ontada again and finish within ten minutes.",
            status=400, code="ontada_state_expired",
        )
    try:
        tok = await ontada.exchange_code(code, state)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc
    await _store_token(session, tok)
    return await status(session)


async def _token(session: AsyncSession) -> dict:
    """A live token dict in the shape integrations.ontada expects, refreshed
    when it has aged out."""
    row = await session.get(db.OAuthToken, TOKEN_ID)
    if row is None:
        raise ApiError(
            "Not connected to Ontada. Call GET /api/ontada/authorize and open the "
            "returned URL in a browser — the gateway supports authorization_code only.",
            status=428, code="ontada_not_connected",
        )

    tok = {
        "access_token": row.access_token,
        "refresh_token": row.refresh_token,
        "patient": row.patient_id,
        "fhir_base": row.fhir_base,
        "expires_at": db.as_aware(row.expires_at).timestamp(),
        **(row.raw or {}),
    }
    # The keeper normally renews well before this point; this stays as the
    # backstop for the first request after a restart, or if the loop is off.
    if not token_keeper.due(row):
        return tok

    if not row.refresh_token:
        raise ApiError(
            "Ontada token expired and no refresh token is stored. Re-run the browser "
            "authorization with the `offline_access` scope.",
            status=428, code="ontada_reauth_required",
        )
    if token_keeper.reauth_required(row):
        # The authorization server has already discarded this refresh token.
        # Asking again cannot help, and a 502 would read like an outage rather
        # than what it is: one browser login needed.
        raise ApiError(
            "The Ontada grant was rejected — its refresh token is no longer valid, so "
            "a practitioner must sign in once more. Open GET /api/ontada/authorize in "
            "a browser. Records already imported stay readable.",
            status=428, code="ontada_reauth_required",
        )
    try:
        return await token_keeper.refresh_and_store(session, row, reason="on-demand")
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc


def _fhir_user(raw: dict) -> str | None:
    """Read the `fhirUser` claim out of the id_token without verifying it.

    Not a security check — the token came straight from the token endpoint over
    TLS and is used only for display. Never trust this for authorisation.
    """
    tok = raw.get("id_token")
    if not tok or tok.count(".") != 2:
        return None
    body = tok.split(".")[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return None
    return claims.get("fhirUser") or claims.get("profile") or claims.get("sub")


@router.get("/status", responses={200: {"model": S.OntadaStatus}})
async def status(session: AsyncSession = Depends(db.get_session)):
    row = await session.get(db.OAuthToken, TOKEN_ID)
    base = {
        "configured": ontada.configured(),
        "fhir_base": config.ONTADA_FHIR_BASE or None,
        "grant_types": ["authorization_code"],
        "launch_context": "standalone-provider",
        "panel_search_supported": True,
        "panel_search_reason": (
            "MEASURED 2026-09-13: connected with user/* scopes as "
            "practitioner-aakash@. `GET /Patient?_summary=count` returns 224, so "
            "the clinician's whole panel is searchable. There is deliberately no "
            "patient context — requesting launch/patient sends the browser into "
            "Ontada's smart_context_resolver, which loops until the browser gives "
            "up, so we read by explicit patient id instead."
        ),
    }
    if row is None:
        return {**base, "connected": False,
                "reason": "No one has completed the SMART browser login yet."}
    return {
        **base,
        "connected": True,
        "expired": db.as_aware(row.expires_at) <= db.utcnow(),
        "can_refresh": bool(row.refresh_token),
        "expires_at": db.as_aware(row.expires_at).isoformat(),
        "scope": row.scope,
        "patient_context": row.patient_id,
        # `fhirUser` is the one thing an SSO-only grant does tell us: the FHIR
        # reference (Practitioner/… or Patient/…) behind the login.
        "fhir_user": _fhir_user(row.raw or {}),
        # What the background keeper has been doing. `reauth_required` is the
        # one the UI acts on: it means no amount of retrying will reconnect us.
        "keeper": {
            "enabled": bool(config.ONTADA_KEEPALIVE_SECONDS),
            "every_seconds": config.ONTADA_KEEPALIVE_SECONDS,
            "renews_at_t_minus_seconds": config.ONTADA_REFRESH_SKEW_SECONDS,
            **token_keeper.state(row),
            # Recomputed, never merely read back: a stored failure flag must not
            # outrank a token that is currently working.
            "reauth_required": token_keeper.reauth_required(row),
        },
    }


@router.post("/refresh", responses={200: {"model": S.OntadaStatus}, **S.ERRORS})
async def refresh_now(session: AsyncSession = Depends(db.get_session)):
    """Exercise the refresh grant right now, whatever the clock says.

    Ontada does not advertise `refresh_token` in `grant_types_supported`, so
    whether the grant works at all is a measurement, not a documented fact.
    This makes that measurable on demand instead of by waiting out a 30-minute
    token, and gives operations a way to prove a connection before a clinic
    session starts.
    """
    _require_config()
    row = await session.get(db.OAuthToken, TOKEN_ID)
    if row is None or not row.refresh_token:
        raise ApiError(
            "Nothing to refresh — no Ontada grant is stored. Complete the browser "
            "login first: GET /api/ontada/authorize.",
            status=428, code="ontada_not_connected",
        )
    try:
        await token_keeper.refresh_and_store(session, row, reason="manual")
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc
    return await status(session)


def _with_patient(tok: dict, patient_id: str | None) -> dict:
    """Resolve which patient to read, explicit argument winning.

    A provider-scoped token carries NO patient context (requesting
    launch/patient hangs in Ontada's own context resolver — see the module
    docstring), so `patient_id` is how a caller names the chart. Without this
    the null context was interpolated straight into the URL and the gateway was
    asked for `Patient/None`, which 404s with an opaque HAPI OperationOutcome.
    """
    pid = patient_id or tok.get("patient")
    if not pid:
        raise ApiError(
            "No patient specified. This is a provider-scoped connection with no "
            "patient context, so pass ?patient_id=<FHIR Patient id>. Find one "
            "with GET /api/ontada/resource/Patient.",
            status=400, code="patient_id_required")
    return {**tok, "patient": pid}


@router.get("/patients", responses={200: {"model": S.OntadaPatients}, **S.ERRORS})
async def patients(q: str = "", include_logins: bool = False,
                   session: AsyncSession = Depends(db.get_session)):
    """The practitioner's patient panel — the front door to every other read.

    Every chart endpoint needs a `patient_id` because the token carries no
    patient context, and until now the only way to find one was to read raw
    FHIR. This is that lookup.

    Logins are filtered out by default: ~200 of the ~224 records are portal
    accounts with no MR identifier, no birth date and no chart behind them, and
    a picker full of those is worse than no picker. `include_logins=true` shows
    them for anyone debugging the directory itself.
    """
    _require_config()
    tok = await _token(session)
    try:
        # The panel is stable within a clinic session and costs three upstream
        # pages, so it is cached briefly rather than re-read on every keystroke.
        rows = await cache.get_or_set(
            f"ontada:panel:{tok['fhir_base']}", 120.0,
            lambda: ontada.search_panel(tok))
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc

    charts = [r for r in rows if r["has_mrn"]]
    shown = rows if include_logins else charts
    needle = q.strip().lower()
    if needle:
        shown = [r for r in shown
                 if needle in r["name"].lower() or needle in r["mrn"].lower()
                 or needle == r["id"].lower()]
    shown = sorted(shown, key=lambda r: (not r["has_mrn"], r["name"].lower()))
    return {
        "count": len(shown),
        "results": shown[:100],
        "panel_total": len(rows),
        "charts_total": len(charts),
        # Said plainly, because "24 of 224" looks like a bug until you know why.
        "filter_note": (
            f"{len(rows) - len(charts)} of {len(rows)} records in this panel are portal "
            "login accounts with no medical record number and no chart behind them; "
            "they are hidden. Pass include_logins=true to see them."
        ),
    }


@router.get("/record")
async def record(patient_id: str | None = None,
                 session: AsyncSession = Depends(db.get_session)):
    """A patient's oncology record, straight from iKnowMed.

    Per-resource read failures are reported in `errors` rather than dropped, so
    "none on file" stays distinguishable from "we could not read it".
    """
    _require_config()
    tok = _with_patient(await _token(session), patient_id)
    try:
        return await ontada.fetch_record(tok)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc


@router.get("/everything")
async def patient_everything(patient_id: str | None = None,
                             session: AsyncSession = Depends(db.get_session)):
    """A patient's entire chart via Patient/$everything."""
    _require_config()
    tok = _with_patient(await _token(session), patient_id)
    try:
        return await ontada.everything(tok)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc


@router.get("/files", responses={200: {"model": S.OntadaFiles}, **S.ERRORS})
async def files(patient_id: str | None = None,
                session: AsyncSession = Depends(db.get_session)):
    """Every attachment on the chart — pathology PDFs, scanned notes, imaging.

    Metadata only. `binary_id` is the handle for GET /api/ontada/file/{id}.
    """
    _require_config()
    tok = _with_patient(await _token(session), patient_id)
    try:
        return await ontada.list_files(tok)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc


@router.get("/file/{binary_id}", response_class=Response, responses={
    200: {"content": {"application/octet-stream": {}},
          "description": "The attachment's bytes, with its real content type."},
    **S.ERRORS})
async def file_bytes(binary_id: str, download: bool = False,
                     session: AsyncSession = Depends(db.get_session)):
    """One attachment's actual bytes, streamed through with its content type.

    Proxied rather than redirected: the browser has no Ontada token, so a
    redirect to the FHIR server would simply 401.
    """
    _require_config()
    tok = await _token(session)
    try:
        raw, ctype = await ontada.fetch_binary(binary_id, tok)
    except ontada.OntadaMissing as exc:
        # 404, not 502: the EHR answered correctly, it simply has no such file.
        raise ApiError(str(exc), status=404, code="attachment_missing") from exc
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc

    ext = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg",
           "text/plain": "txt", "text/html": "html"}.get(ctype.split(";")[0], "bin")
    # `inline` lets the viewer render a PDF or image in place; `download` is for
    # attaching the file to a package.
    disposition = "attachment" if download else "inline"
    return Response(content=raw, media_type=ctype, headers={
        "Content-Disposition": f'{disposition}; filename="{binary_id}.{ext}"',
        "Cache-Control": "private, max-age=300",
    })


@router.get("/summary", responses={200: {"model": S.OntadaSummary}, **S.ERRORS})
async def summary(patient_id: str | None = None, casebook_id: str | None = None,
                  session: AsyncSession = Depends(db.get_session)):
    """The chart phrased as a clinical picture, not a resource count.

    Deterministic: every line is assembled from fields that are present, so any
    figure traces back to a resource. Absent fields are reported in `gaps`
    rather than filled in — see services/clinical_summary.py.

    `casebook_id` lets values a person supplied count towards the gaps. Only the
    stage is taken today, because it is the one thing the payer needs that this
    EHR does not carry anywhere, and it comes back labelled `entered by hand` so
    it is never mistaken for something the chart said.
    """
    _require_config()
    tok = _with_patient(await _token(session), patient_id)
    cb = await session.get(db.Casebook, casebook_id) if casebook_id else None
    try:
        record = await ontada.everything(tok)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc
    return clinical_summary.summarise(
        record["resources"], casebook={"stage": cb.stage} if cb else None)


@router.post("/import", status_code=201, responses={201: {"model": S.OntadaImport}, **S.ERRORS})
async def import_patient(patient_id: str | None = None,
                         session: AsyncSession = Depends(db.get_session)):
    """Pull a patient's chart and create a casebook from it.

    One call: $everything -> map -> casebook (+ a pre-auth package when the
    bundle carried a usable Coverage). Fields the bundle does not fill are
    returned in `unmapped` so the UI can show them as gaps rather than letting
    a blank pass for a value.
    """
    _require_config()
    tok = _with_patient(await _token(session), patient_id)
    try:
        record = await ontada.everything(tok)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc

    try:
        mapped = fhir_import.to_casebook(record["resources"])
    except ValueError as exc:
        raise ApiError(str(exc), status=422, code="unmappable_bundle") from exc

    fields, coverage = mapped["casebook"], mapped["coverage"]
    fhir_id = fields.get("ontada_fhir_id")

    existing = (await session.execute(
        db.select(db.Casebook).where(db.Casebook.ontada_fhir_id == fhir_id)
    )).scalars().first() if fhir_id else None

    cb = existing or db.Casebook(id=f"cb-{uuid.uuid4().hex[:8]}")
    if existing is None:
        session.add(cb)
    for k, v in fields.items():
        if v:
            setattr(cb, k, v)
    # First guess only; every read recomputes it from what the record holds by
    # then, so filling a gap later clears the label — see services/casebook_gaps.
    cb.status = "ai-ready" if not mapped["unmapped"] else "gaps-pending"
    cb.fhir_snapshot = {"counts": record["counts"], "pages": record.get("pages"),
                        "withheld_note": record.get("withheld_note")}
    await session.flush()

    pkg = None
    if coverage.get("member_id"):
        pkg = db.PreAuthPackage(
            id=f"pa-{uuid.uuid4().hex[:8]}", casebook_id=cb.id,
            patient_name=cb.patient_name, mrn=cb.mrn,
            payer_name=coverage["payer_name"], member_id=coverage["member_id"],
            group_number=coverage["group_number"], hospital_id=cb.hospital_id,
            lines=[], evidence=[],
            events=[{"id": uuid.uuid4().hex[:8], "at": db.utcnow().isoformat(),
                     "actor": "Ontada", "kind": "success",
                     "action": "Coverage imported from the FHIR Coverage resource",
                     "detail": f"{coverage['payer_name']} · member {coverage['member_id']}"}],
        )
        session.add(pkg)

    await session.commit()
    return {
        "casebook_id": cb.id,
        "created": existing is None,
        "package_id": pkg.id if pkg else None,
        "counts": record["counts"],
        "coverage": coverage,
        "unmapped": mapped["unmapped"],
        "withheld_note": record.get("withheld_note"),
    }


@router.get("/resource/{resource_type}")
async def resource(resource_type: str, patient_id: str | None = None,
                   session: AsyncSession = Depends(db.get_session)):
    """Every page of one resource type for one patient.

    `patient_id` is required in practice: integrations.ontada.fetch puts it in
    the `patient` search parameter, and with a provider-scoped token that was
    None — so the gateway ignored the filter and returned the WHOLE store
    (110 Conditions across all patients, not the 5 for this one).
    """
    _require_config()
    tok = _with_patient(await _token(session), patient_id)
    try:
        items = await ontada.fetch(resource_type, tok)
    except Exception as exc:
        raise UpstreamError("ontada", str(exc)) from exc
    return {"resourceType": resource_type, "count": len(items), "items": items,
            "withheld_note": ontada.withheld_note()}
