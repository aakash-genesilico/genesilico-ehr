"""Ontada / iKnowMed G2 FHIR R4 — real patient-authorised EHR access.

Texas Oncology (and the rest of The US Oncology Network) run on iKnowMed
Generation 2, which is ONC-certified for 170.315(g)(10) — Drummond cert
15.04.04.2920.iKno.30.01.1.180508. Holding (g)(10) obliges the module to
support SMART App Launch `launch-standalone` + `context-standalone-patient`,
i.e. exactly the flow below: the patient logs in at their own practice and
authorises this app against their own record.

There are no API keys here. Access is an OAuth 2.0 authorization-code grant
with PKCE; the bearer token is minted only after the patient authenticates.
Nothing is fabricated — every field returned came out of the practice's FHIR
server, and when a resource is absent or withheld we say so.

One honest caveat, documented by Ontada: the server "may intentionally
withhold certain data elements based on iKnowMed (iKM) G2 clinical workflows
and applicable regulatory or state-level requirements" on DiagnosticReport,
DocumentReference and Observation. `withheld_note()` surfaces that to callers
rather than letting a caller read a short list as a complete one.

Docs:     https://developer-portal.ontada.com/docs/fhir-apis-documentation
Register: https://apiaccess.mckesson.com/apiportal-service/  (apiaccess@mckesson.com)
"""
import base64
import hashlib
import os
import secrets
import time

import httpx

from .. import config
from . import ontada_keys


class OntadaError(RuntimeError):
    """Raised with the server's own message — never a substituted value."""


class OntadaMissing(OntadaError):
    """The server does not have a resource the chart references.

    Distinct from a failed read: Ontada's own data carries dangling attachment
    references (a DocumentReference pointing at a Binary the store answers
    HAPI-2001 "is not known" for), and telling a user "the chart references a
    file the EHR cannot produce" is honest where a 502 would blame us.
    """


# SMART scopes for a standalone patient launch. `offline_access` is what earns
# the refresh token; without it the patient re-authenticates every hour.
#
# iKnowMed is registered at SMART 2.0.0, whose scope syntax is `.rs` (r=read,
# s=search) rather than v1's `.read`. A v2 server may still honour v1 scopes for
# back-compat, but we send what the registration declares. `SCOPES_V1` is kept
# as a documented fallback for a server that advertises only `permission-v1` in
# its smart-configuration `capabilities`.
_RESOURCES = ("Patient", "Condition", "Procedure", "Observation",
              "DiagnosticReport", "DocumentReference", "MedicationRequest",
              "MedicationStatement", "AllergyIntolerance", "Immunization",
              "Encounter", "CarePlan", "CareTeam", "Goal", "Coverage",
              "Specimen")
_BASE_SCOPES = "launch/patient openid fhirUser offline_access"

SCOPES = " ".join([_BASE_SCOPES] + [f"patient/{r}.rs" for r in _RESOURCES])
SCOPES_V1 = " ".join([_BASE_SCOPES] + [f"patient/{r}.read" for r in _RESOURCES])


def scopes_for(cfg: dict) -> str:
    """Pick v2 or v1 scope syntax from the server's advertised capabilities.

    ONTADA_SCOPES overrides both. The gateway's `capabilities` describe what the
    SERVER supports, not what THIS registration was granted, and asking for one
    scope outside the grant fails the whole request with [invalid_scope].
    """
    if config.ONTADA_SCOPES:
        return config.ONTADA_SCOPES
    caps = cfg.get("capabilities") or []
    if "permission-v2" in caps:
        return SCOPES
    if "permission-v1" in caps:
        return SCOPES_V1
    return SCOPES          # registered as SMART 2.0.0; v2 is the default

# Resources worth pulling for an oncology record, in the order they are useful.
ONCOLOGY_RESOURCES = ("Condition", "Procedure", "MedicationRequest",
                      "MedicationStatement", "MedicationAdministration",
                      "MedicationDispense", "Observation", "DiagnosticReport",
                      "DocumentReference", "Encounter", "CarePlan", "CareTeam",
                      "Goal", "Specimen", "AllergyIntolerance", "Immunization",
                      "Coverage", "ServiceRequest", "Device",
                      "QuestionnaireResponse", "RelatedPerson", "Provenance")

# Resource types whose attachments carry an actual file. Binary is fetched by
# id (the grant is `.r`, read-only, no search), which is exactly how
# DocumentReference.content.attachment.url addresses it.
ATTACHMENT_SOURCES = ("DocumentReference", "DiagnosticReport")

# Pending authorisations, keyed by OAuth `state`. Process-local and short-lived
# by design: a PKCE verifier must never outlive the redirect that consumes it.
_PENDING: dict[str, dict] = {}
_PENDING_TTL = 600


def configured() -> bool:
    return bool(config.ONTADA_CLIENT_ID and config.ONTADA_FHIR_BASE)


def _needs_credential() -> OntadaError:
    return OntadaError(
        "Ontada/iKnowMed needs ONTADA_CLIENT_ID and ONTADA_FHIR_BASE. Register a "
        "patient-facing app at https://apiaccess.mckesson.com/apiportal-service/ "
        "— iKnowMed issues a unique client identifier per app and provides a "
        "FHIR sandbox. Ask apiaccess@mckesson.com for the practice's service "
        "base URL if the portal does not list it.")


# --------------------------------------------------------------------------- #
# Client authentication. Ontada registers an app as one of three client types
# and the token request differs for each:
#   asymmetric  private_key_jwt  — a signed assertion, no secret in transit
#   symmetric   client_secret    — HTTP Basic
#   public      PKCE only        — no client credential at all
# ONTADA_CLIENT_AUTH pins the mode so a misconfigured .env fails loudly rather
# than silently downgrading to a weaker method.
# --------------------------------------------------------------------------- #
JWT_BEARER = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def auth_mode() -> str:
    mode = (config.ONTADA_CLIENT_AUTH or "").strip().lower()
    if mode in ("asymmetric", "symmetric", "public"):
        return mode
    return "symmetric" if config.ONTADA_CLIENT_SECRET else "asymmetric"


def _client_auth(data: dict, token_url: str) -> tuple[dict, tuple | None]:
    mode = auth_mode()
    if mode == "asymmetric":
        data = {**data, "client_assertion_type": JWT_BEARER,
                "client_assertion": ontada_keys.client_assertion(token_url)}
        return data, None
    if mode == "symmetric":
        if not config.ONTADA_CLIENT_SECRET:
            raise OntadaError(
                "ONTADA_CLIENT_AUTH=symmetric but ONTADA_CLIENT_SECRET is unset.")
        return data, (config.ONTADA_CLIENT_ID, config.ONTADA_CLIENT_SECRET)
    return data, None          # public client — PKCE is the only protection


# --------------------------------------------------------------------------- #
# Discovery — never hardcode /authorize or /token. Ontada publishes both via
# the standard SMART discovery documents and reserves the right to move them.
# --------------------------------------------------------------------------- #
_CONF: dict[str, tuple[float, dict]] = {}
_CONF_TTL = 3600


async def smart_config(fhir_base: str = "") -> dict:
    base = (fhir_base or config.ONTADA_FHIR_BASE).rstrip("/")
    if not base:
        raise _needs_credential()
    hit = _CONF.get(base)
    if hit and time.time() - hit[0] < _CONF_TTL:
        return hit[1]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{base}/.well-known/smart-configuration",
                        headers={"Accept": "application/json"})
        if r.status_code == 403:
            raise OntadaError(
                f"{base}/.well-known/smart-configuration returned 403. The "
                "gateway is denying this caller, not reporting a missing "
                "document — ask apiaccess@mckesson.com whether your client id "
                "and egress IP need allowlisting for this environment. Note "
                "that (g)(10) expects SMART discovery to be reachable.")
        if r.status_code >= 400:
            raise OntadaError(f"SMART discovery failed: {r.status_code} {r.text[:300]}")
        cfg = r.json()
    for key in ("authorization_endpoint", "token_endpoint"):
        if not cfg.get(key):
            raise OntadaError(f"SMART discovery is missing {key}: {cfg}")
    _CONF[base] = (time.time(), cfg)
    return cfg


# --------------------------------------------------------------------------- #
# Step 1 — send the patient to their practice to log in
# --------------------------------------------------------------------------- #
def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


async def authorize_url(fhir_base: str = "", redirect_uri: str = "") -> dict:
    """Build the patient's login URL. Returns {url, state}."""
    if not configured():
        raise _needs_credential()
    base = (fhir_base or config.ONTADA_FHIR_BASE).rstrip("/")
    redirect = redirect_uri or config.ONTADA_REDIRECT_URI
    cfg = await smart_config(base)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)

    now = time.time()
    for k, v in list(_PENDING.items()):          # drop expired verifiers
        if now - v["created"] > _PENDING_TTL:
            _PENDING.pop(k, None)
    scope = scopes_for(cfg)
    _PENDING[state] = {"verifier": verifier, "fhir_base": base,
                       "redirect_uri": redirect, "created": now, "scope": scope}

    params = httpx.QueryParams({
        "response_type": "code",
        "client_id": config.ONTADA_CLIENT_ID,
        "redirect_uri": redirect,
        "scope": scope,
        "state": state,
        "aud": base,                             # required by SMART App Launch
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"url": f"{cfg['authorization_endpoint']}?{params}", "state": state}


# --------------------------------------------------------------------------- #
# Step 2 — the practice redirects back with a code; swap it for tokens
# --------------------------------------------------------------------------- #
def has_pending(state: str) -> bool:
    """Whether this `state` still has a live PKCE verifier in this process.

    Lets a caller tell a lapsed login window apart from a gateway failure —
    they need opposite responses: start again here, versus wait and retry.
    """
    pending = _PENDING.get(state)
    return bool(pending) and (time.time() - pending["created"]) <= _PENDING_TTL


async def exchange_code(code: str, state: str) -> dict:
    pending = _PENDING.pop(state, None)
    if not pending:
        raise OntadaError(
            "Unknown or expired OAuth state. Restart the authorisation — a PKCE "
            "verifier is single-use and expires after 10 minutes.")
    cfg = await smart_config(pending["fhir_base"])
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "client_id": config.ONTADA_CLIENT_ID,
        "code_verifier": pending["verifier"],
    }
    data, auth = _client_auth(data, cfg["token_endpoint"])
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(cfg["token_endpoint"], data=data, auth=auth,
                         headers={"Accept": "application/json"})
    if r.status_code >= 400:
        raise OntadaError(f"Token exchange failed: {r.status_code} {r.text[:400]}")
    tok = r.json()
    # Only a launch/patient request promises a patient context. An SSO-only
    # grant (openid fhirUser) legitimately returns none, and rejecting that
    # would throw away a token that still identifies who logged in.
    if "launch/patient" in pending.get("scope", "") and not tok.get("patient"):
        raise OntadaError(
            "Token response carried no `patient` launch context. Confirm the "
            "app is registered for standalone patient launch and that "
            "`launch/patient` was granted.")
    tok["fhir_base"] = pending["fhir_base"]
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    return tok


async def refresh(token: dict) -> dict:
    """Renew with the refresh token earned by `offline_access`."""
    if not token.get("refresh_token"):
        raise OntadaError("No refresh_token — request the `offline_access` scope.")
    cfg = await smart_config(token["fhir_base"])
    data, auth = _client_auth({
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
        "client_id": config.ONTADA_CLIENT_ID,
    }, cfg["token_endpoint"])
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(cfg["token_endpoint"], auth=auth, data=data)
    if r.status_code >= 400:
        raise OntadaError(f"Refresh failed: {r.status_code} {r.text[:300]}")
    new = {**token, **r.json()}
    new["expires_at"] = time.time() + int(new.get("expires_in", 3600)) - 60
    return new


# --------------------------------------------------------------------------- #
# Step 3 — read the record
# --------------------------------------------------------------------------- #
async def _get(client: httpx.AsyncClient, url: str, token: dict) -> dict:
    r = await client.get(url, headers={
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/fhir+json",
    })
    if r.status_code == 401:
        raise OntadaError("401 from the FHIR server — token expired; call refresh().")
    if r.status_code == 403:
        raise OntadaError(
            f"403 on {url}. Either the scope was not granted or iKnowMed is "
            "withholding this resource from patient-facing access.")
    if r.status_code == 429:
        raise OntadaError("429 — Ontada rate limit hit. Back off and retry.")
    if r.status_code >= 400:
        raise OntadaError(f"{r.status_code} on {url}: {r.text[:300]}")
    return r.json()


async def fetch(resource: str, token: dict, *, page_limit: int = 20,
                **search) -> list[dict]:
    """Read every page of one resource type for the patient in launch context.

    Ontada's `next` links stay valid for 8 hours and must be followed as given.
    """
    base = token["fhir_base"].rstrip("/")
    params = {"patient": token["patient"], "_count": 100, **search}
    url = f"{base}/{resource}?{httpx.QueryParams(params)}"
    out, pages = [], 0
    async with httpx.AsyncClient(timeout=60) as c:
        while url and pages < page_limit:
            bundle = await _get(c, url, token)
            out += [e["resource"] for e in bundle.get("entry", [])
                    if e.get("resource")]
            url = next((l["url"] for l in bundle.get("link", [])
                        if l.get("relation") == "next"), None)
            pages += 1
    return out


async def everything(token: dict, page_limit: int = 30) -> dict:
    """`Patient/$everything` — the whole chart in one call.

    The gateway's CapabilityStatement advertises this operation on Patient
    (verified 2026-09-09), and it is far cheaper than walking each resource
    type. Falls back to nothing: callers keep fetch_record() for servers that
    do not implement it.
    """
    base = token["fhir_base"].rstrip("/")
    url = f"{base}/Patient/{token['patient']}/$everything?_count=100"
    out: dict[str, list] = {}
    pages = 0
    async with httpx.AsyncClient(timeout=90) as c:
        while url and pages < page_limit:
            bundle = await _get(c, url, token)
            for e in bundle.get("entry", []):
                r = e.get("resource") or {}
                if r.get("resourceType"):
                    out.setdefault(r["resourceType"], []).append(r)
            url = next((l["url"] for l in bundle.get("link", [])
                        if l.get("relation") == "next"), None)
            pages += 1
    return {"resources": out, "counts": {k: len(v) for k, v in out.items()},
            "pages": pages, "withheld_note": withheld_note()}


async def fetch_record(token: dict,
                       resources: tuple[str, ...] = ONCOLOGY_RESOURCES) -> dict:
    """Pull the oncology-relevant record. Per-resource failures are reported,
    never silently dropped — a caller must be able to tell "none on file" from
    "we could not read it"."""
    patient = await _get_patient(token)
    out: dict = {"patient": patient, "resources": {}, "errors": {},
                 "withheld_note": withheld_note(), "fhir_base": token["fhir_base"]}
    for rtype in resources:
        try:
            out["resources"][rtype] = await fetch(rtype, token)
        except OntadaError as e:
            out["errors"][rtype] = str(e)
    out["counts"] = {k: len(v) for k, v in out["resources"].items()}
    return out


async def search_panel(token: dict, page_limit: int = 5) -> list[dict]:
    """Every patient this practitioner can see, as flat rows.

    Deliberately not `fetch()`: that pins `patient=<id>` on every request, which
    is meaningless when the patient is what we are looking for.

    MEASURED 2026-09-13: `/Patient` returns ~224 records that are two different
    populations. Around 200 are portal login accounts — UUID ids, no birth date,
    no gender, no MR identifier — and they bury the handful of real charts. The
    `has_mrn` flag below is what tells them apart; the caller decides whether to
    show the rest, but nothing should default to a list that is 90% noise.
    """
    base = token["fhir_base"].rstrip("/")
    url = f"{base}/Patient?_count=100"
    rows, pages = [], 0
    async with httpx.AsyncClient(timeout=60) as c:
        while url and pages < page_limit:
            bundle = await _get(c, url, token)
            for e in bundle.get("entry", []):
                r = e.get("resource") or {}
                if r.get("resourceType") != "Patient":
                    continue
                rows.append(_patient_row(r))
            url = next((l["url"] for l in bundle.get("link", [])
                        if l.get("relation") == "next"), None)
            pages += 1
    return rows


def _patient_row(r: dict) -> dict:
    name = (r.get("name") or [{}])[0]
    given = " ".join(name.get("given") or [])
    family = name.get("family") or ""
    mrn = next((i.get("value") for i in (r.get("identifier") or [])
                if (i.get("type", {}).get("coding") or [{}])[0].get("code") == "MR"), "")
    return {
        "id": r.get("id", ""),
        "name": f"{given} {family}".strip() or name.get("text") or "",
        "mrn": mrn or "",
        "birth_date": r.get("birthDate") or "",
        "gender": r.get("gender") or "",
        # A real chart carries a medical record number. A login account does not.
        "has_mrn": bool(mrn),
    }


async def _get_patient(token: dict) -> dict:
    base = token["fhir_base"].rstrip("/")
    async with httpx.AsyncClient(timeout=30) as c:
        return await _get(c, f"{base}/Patient/{token['patient']}", token)


async def document(token: dict, doc_ref: dict) -> list[dict]:
    """Resolve a DocumentReference's attachments to bytes.

    Pathology, staging and molecular reports usually live here as PDFs rather
    than in discrete fields, so an oncology record is incomplete without them.
    """
    base = token["fhir_base"].rstrip("/")
    out = []
    async with httpx.AsyncClient(timeout=60) as c:
        for content in doc_ref.get("content", []):
            att = content.get("attachment", {})
            if att.get("data"):
                out.append({"content_type": att.get("contentType"),
                            "title": att.get("title"),
                            "bytes": base64.b64decode(att["data"])})
                continue
            url = att.get("url")
            if not url:
                continue
            if not url.startswith("http"):
                url = f"{base}/{url.lstrip('/')}"
            r = await c.get(url, headers={
                "Authorization": f"Bearer {token['access_token']}",
                "Accept": att.get("contentType") or "application/octet-stream"})
            if r.status_code >= 400:
                continue
            out.append({"content_type": att.get("contentType"),
                        "title": att.get("title"), "bytes": r.content})
    return out


def withheld_note() -> str:
    return ("Ontada documents that iKnowMed G2 may intentionally withhold "
            "elements of DiagnosticReport, DocumentReference and Observation "
            "from patient-facing access, per clinical workflow and state rules. "
            "Treat these lists as possibly partial, not as the complete record; "
            "a HIPAA right-of-access request returns what the API does not.")


# --------------------------------------------------------------------------- #
# Files. DocumentReference and DiagnosticReport point at the real artefacts —
# pathology PDFs, scanned operation notes, imaging. Measured against Ontada
# 2026-09-13: attachments carry no inline `data` and no `size`, only a
# `url` of the form "Binary/<id>", so the bytes need a second fetch.
# --------------------------------------------------------------------------- #
def _attachments_of(resource: dict) -> list[dict]:
    """Every attachment on one resource, normalised to a flat record."""
    out: list[dict] = []
    kind = resource.get("resourceType", "")
    holders = (resource.get("content") or []) if kind == "DocumentReference" else []
    atts = [c.get("attachment") or {} for c in holders]
    if kind == "DiagnosticReport":
        atts += resource.get("presentedForm") or []

    for a in atts:
        url = a.get("url") or ""
        # A relative "Binary/<id>" is ours to fetch. An absolute URL is a
        # different host's, and we record it without following it — chasing an
        # arbitrary URL out of a payload is how an SSRF starts.
        binary_id = url.split("Binary/", 1)[1].strip("/") if "Binary/" in url else ""
        out.append({
            "binary_id": binary_id,
            "url": url,
            "content_type": a.get("contentType") or "",
            "title": a.get("title") or "",
            "size": a.get("size"),
            "created": a.get("creation") or "",
            "has_inline_data": bool(a.get("data")),
            # A HANDLE we can attempt, not a promise the bytes exist: Ontada's
            # data contains references to Binaries the store does not hold, and
            # only the fetch reveals which. Never render this as "available".
            "addressable": bool(binary_id) or bool(a.get("data")),
        })
    return out


async def list_files(token: dict) -> dict:
    """Every attachment on the patient's chart, with its source resource.

    Metadata only — the bytes are not pulled here. One chart can carry tens of
    megabytes of scans, and a list view never needs them.
    """
    files: list[dict] = []
    errors: dict[str, str] = {}
    for kind in ATTACHMENT_SOURCES:
        try:
            items = await fetch(kind, token)
        except Exception as exc:
            errors[kind] = str(exc)
            continue
        for r in items:
            label = ((r.get("type") or {}).get("text")
                     or (r.get("code") or {}).get("text") or "")
            for att in _attachments_of(r):
                files.append({
                    **att,
                    "source_type": kind,
                    "source_id": r.get("id") or "",
                    "label": att["title"] or label or "Untitled",
                    "date": (r.get("date") or r.get("issued")
                             or r.get("effectiveDateTime") or "")[:10],
                    "status": r.get("status") or "",
                })
    files.sort(key=lambda f: f["date"], reverse=True)
    return {"count": len(files), "files": files, "errors": errors,
            "withheld_note": withheld_note()}


async def fetch_binary(binary_id: str, token: dict) -> tuple[bytes, str]:
    """One attachment's bytes and content type.

    Ontada answers a Binary read with a FHIR Binary resource carrying base64
    `data` whatever Accept header is sent — verified 2026-09-13, an
    `Accept: application/pdf` still returns application/fhir+json. So decode
    rather than trusting the response's own content type.
    """
    import base64

    base = token["fhir_base"].rstrip("/")
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(f"{base}/Binary/{binary_id}", headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/fhir+json",
        })
    if r.status_code == 404:
        raise OntadaMissing(
            f"The chart references Binary/{binary_id} but the EHR does not have "
            "it. This is a dangling reference in the source data, not a failed "
            "read — nothing we can retry will produce the file.")
    if r.status_code >= 400:
        raise OntadaError(f"{r.status_code} on Binary/{binary_id}: {r.text[:300]}")

    ctype = r.headers.get("content-type", "")
    if "fhir+json" in ctype or "application/json" in ctype:
        body = r.json()
        data = body.get("data")
        if not data:
            raise OntadaError(
                f"Binary/{binary_id} came back with no `data`. The server may be "
                "withholding the content rather than failing to find it.")
        return base64.b64decode(data), body.get("contentType") or "application/octet-stream"
    # A server that does return raw bytes is equally valid FHIR; honour it.
    return r.content, ctype or "application/octet-stream"
