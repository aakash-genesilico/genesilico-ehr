# genesilico-ehr

EHR connectivity, casebook intake and pre-authorization for **Texas Oncology**,
whose charts live in **Ontada (iKnowMed)**.

```bash
# backend  (FastAPI, port 8090)
cd backend && python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python seed.py
./.venv/bin/python -m uvicorn app.main:app --port 8090

# frontend (Next.js, port 3045)
npm install && npm run dev      # http://localhost:3045/ehr
```

`GET /api/capabilities` is the authoritative statement of what this deployment
can do. The UI reads it and disables what is not wired.

## What is real

Verified live, not assumed — Stedi on **9 Sep 2026**, Ontada on **13 Sep 2026**.

| Capability | Status | Evidence |
|---|---|---|
| Stedi payer directory | **Real** | Returns live payer IDs (UnitedHealthcare `87726`, Aetna `60054`) |
| Stedi eligibility 270/271 | **Real** | Production key returns `applicationMode: production`; reached real UHC |
| Stedi claim status 276/277 | **Real**, production key only | 403 in test mode, 400 (validating) in production |
| Stedi insurance discovery | **Real**, production key only | Same |
| Ontada FHIR gateway | **Connected** | Signed in 13 Sep 2026 as `practitioner-aakash@`; 224 patients readable |
| Ontada SMART OAuth | **Real** | Private (Symmetric) + PKCE. The refresh token **rotates on every renewal** and Ontada publishes no lifetime for it, so an idle grant dies — left unused ~30 h it returned `400 [invalid_grant]`. `services/token_keeper` renews every 5 min, at T-10 min, so it never goes idle |
| Ontada documents | **Real** | 44 attachments referenced, **34 retrievable** as actual PDFs and scanned images |
| Ontada patient context | **Unusable** | `launch/patient` loops forever in Ontada's own context resolver — see below |
| **Prior auth (X12 278)** | **Does not exist** | Every candidate path 404s on **both** keys |
| CancerAI / Digital Twin | **Not wired** | Lives in gSage; no endpoint connected here |

### Four constraints that shape the product

**1. There is no 278 endpoint on Stedi.** Prior-authorisation submission cannot
happen through this integration. `POST /api/preauth/{id}/submit` returns **501**
with the reason rather than minting an authorisation number nobody issued.
Real submission needs a clearinghouse that carries 278, the payer's portal, or
a Da Vinci PAS FHIR endpoint.

**2. Ontada supports `authorization_code` only.** No `client_credentials`, so a
server cannot authenticate by itself. A human signs in once in a browser and the
`offline_access` refresh token keeps the backend running after that. The
authorize endpoint is behind an Imperva WAF, so the redirect must happen in a
real browser tab — curl gets a 403.

**3. The connection is provider-scoped, and `launch/patient` is unusable.**
Requesting it hands the browser to Ontada's `smart_context_resolver`, which
redirects to itself accumulating one `launch=<uuid>` per hop until the browser
aborts at ~20 with "too many redirects". That loop is inside *their* client, so
we avoid the scope rather than fix it. The token therefore carries **no patient
context**, and every read names its patient explicitly (`?patient_id=`). This
costs nothing: `user/*` scopes read the whole panel, and pre-auth staff need to
*search* for a patient, which a patient-context token could never do.

**4. A grant is all-or-nothing.** The authorization server rejects the **whole**
request with `[invalid_scope]` if one element sits outside the registration —
there is no partial grant. `ONTADA_SCOPES` pins the exact verified string. Two
traps inside it: `launch` needs an in-EHR launch token we never have, and
`Binary` is granted `.r` only (read by id, no search), so asking for `.rs`
fails everything.

### Real vs derived, on the coverage screen

A 271 describes the **benefit**. It does not adjudicate a specific HCPCS or CPT
code. So the API separates the two:

- **Payer-stated** (real): active/inactive, deductible, OOP max, coinsurance,
  copay, and the payer's own AAA rejection text.
- **Estimated** (our arithmetic, labelled as such): what a billed line costs the
  patient, from applying that coinsurance/copay to the line.

No line is ever marked "denied" — unknown stays `unknown`. Verified against the
Aetna fixture: 0% coinsurance on the drug line → $0, $25 copay applied once to
the encounter line, not to every line.

## What the EHR connection gives you

Measured 13 Sep 2026 against the live gateway, not assumed.

```
fhirUser        Practitioner/0481e0c1-8855-4e56-920a-4d12ab7fa8a0  ("Aakash G")
patient panel   224 patients, searchable
patient context none, by design (see constraint 3)
```

The store is **not** the empty smoke-test repository the tenant name
(`test-ui_smoke`) suggests: 2,245 Observations, 2,025 MedicationRequests, 912
Encounters, 383 DiagnosticReports, 333 DocumentReferences, 110 Conditions, 23
Coverages.

### The patient to build against

`Patient/EAAB756F4ECC462DB72ACDF47546F912` — "PatCert Pat zzAdult", MR
`certadult`. Ontada's ONC **(g)(10) certification** patient, and the only fully
populated one. A real colorectal oncology chart: primary malignant neoplasm of
colon (C18.2) and rectum (C20), on **Cetuximab IV** (RxNorm 318341, 6 orders,
loading dose then weekly maintenance), with Granisetron, Dexamethasone and
Prednisone alongside. Coverage carries payer **zzAetna**, member, plan and group
— the four fields staff retype by hand today.

> A near-identical duplicate sits at `Patient/21454`, differing only in city.
> Pick one and stay on it.

### Two populations of Patient

`/Patient` returns two shapes, and only one is clinical:

- **UUID ids** with a `portal/user-id` identifier, no gender, no DOB — portal
  *login accounts*, not charts. `patient-aakash@genesilico.ai` is one of these:
  a name, an email, and no medical record at all.
- **Uppercase-hex or numeric ids** with an `MR` identifier, gender and DOB — the
  real iKnowMed-shaped records.

A patient picker must filter on the presence of an `MR` identifier, or ~200
login accounts drown the handful of real charts.

### Files are real, and 23% of them are not there

`DocumentReference.content.attachment` and `DiagnosticReport.presentedForm`
carry no inline data — only a `Binary/<id>` pointer, so the bytes need a second
fetch. `GET /api/ontada/file/{binary_id}` does it and proxies the result
(the browser holds no Ontada token, so a redirect would 401).

Of 44 attachments referenced, **34 retrieve** as genuine PDFs and scanned PNGs.
The other 10 are **dangling references** — the chart points at a Binary the
store answers `HAPI-2001: is not known` for. In this dataset the id prefix
predicts it exactly: `Binary/pre…` works, `Binary/FA…` does not, ten out of ten.

So a "documents on file" count taken from DocumentReference alone **overstates
the evidence available by 23%**. Anything promising a payer an attachment must
confirm the fetch, not the reference. The API field is named `addressable` (a
handle worth trying), never `available`, and a missing file returns **404
`attachment_missing`**, not a 502 — the EHR answered correctly, it simply has no
such file.

> Ontada ignores the `Accept` header on a Binary read: asking for
> `application/pdf` still returns `application/fhir+json` with base64 inside.
> The content type must be read from the resource's own `contentType` field.

### ⚠️ A stored XSS payload sits in the patient list

One record's name is literally
`adk<a href=attacker.com>cezeri was here</a>`. Harmless as data, but it is a
live test of whether the UI escapes what it renders. React escapes by default;
the risk is `dangerouslySetInnerHTML`, string-concatenated HTML, and names
rendered into PDF or email templates.

## Connecting to Ontada

The gateway supports `authorization_code` only, so a human signs in once.

```bash
cd backend
./.venv/bin/python connect_ontada.py            # prints the login URL
# open it in a REAL browser — curl gets a 403 from Ontada's Imperva WAF
# sign in as the sandbox practitioner, then:
./.venv/bin/python connect_ontada.py '<paste the URL you landed on>'
```

`offline_access` earns a refresh token, so this is a one-time step — the backend
renews itself thereafter (verified: a token expiring at 05:48 renewed to 06:20
with no browser involved).

Two things that make this harder than it looks, both documented in
`docs/ONTADA-FINDINGS.md`:

- **Loopback redirect URIs are refused by the WAF** before OAuth even runs, so
  `ONTADA_REDIRECT_URI` must be an https value registered in the Ontada portal.
- The registered host may be an **unrelated site** that never receives the code
  — its router can rewrite the URL and discard `?code=` before anyone copies it.
  `connect_ontada.py` exists precisely so the code can be pasted back by hand;
  no hosting and no second app registration is needed.

## Reading the chart

| Endpoint | What it answers |
|---|---|
| `GET /api/ontada/summary?patient_id=` | The chart phrased as a clinical picture, plus the gaps |
| `GET /api/ontada/files?patient_id=` | Every attachment, with a `binary_id` handle |
| `GET /api/ontada/file/{binary_id}` | The actual bytes, proxied with the real content type |
| `GET /api/ontada/record?patient_id=` | 22 oncology resource types, per-type errors reported |
| `GET /api/ontada/everything?patient_id=` | `Patient/$everything` — the whole chart, paged |
| `GET /api/ontada/resource/{type}?patient_id=` | One resource type, every page |
| `POST /api/ontada/import?patient_id=` | Chart → casebook (+ pre-auth package when Coverage is usable) |

`services/clinical_summary.py` builds the summary **deterministically** — no
model, no inference. Every sentence is assembled from fields that are present,
so any figure traces back to a resource id, and a field the chart lacks is
listed in `gaps` rather than filled with a plausible value. It deliberately does
*not* classify drugs as chemotherapy vs supportive care: that needs a drug
database we do not have, and a wrong guess puts the wrong drug on an
authorisation.

## Data

There are **no fixtures**.

- `seed.py` — tenant reference data (the cancer center and its two facilities).
- `seed_patient.py` — **Shaheen Farooq**, a real Texas Oncology patient. Every
  demographic and coverage field is read out of `data/271-shaheen-farooq.json`,
  a production 271 UnitedHealthcare returned through Stedi (701 benefit
  entries). Clinical fields the 271 does not carry — diagnosis, stage,
  oncologist — are left blank rather than guessed.

- Casebooks imported from Ontada are **live EHR reads**, not seeds. Nothing is
  cached to disk; each import re-reads the chart.

> **PHI.** `backend/data/` is gitignored. The stored 271 carries a real
> patient's name, date of birth, home address and member ID; the SQLite database
> carries the same once seeded, **plus the live OAuth access and refresh tokens**
> for the EHR connection. `.gitignore` also excludes `*.pdf`/`*.png`/`*.jpg`
> outside `public/` and `docs/`, because anything saved out of
> `/api/ontada/file/{id}` is a real clinical document. To run `seed_patient.py`
> on another machine, copy the 271 across out of band.

## Reading a real 271

Test fixtures return a handful of benefit lines. This production response
returns 701, and the naive "take the first copay" approach is meaningless
against it. `services/benefits.py` handles the real shape:

- **No coinsurance and no deductible on this plan.** It is copay-driven: 489
  EB=B lines that differ by service type, network, and a free-text label.
- **Oncology is priced by drug tier.** The label carries
  `PROVIDER ADMINISTERED DRUG TIER n` — 21 tiers, each with in- and
  out-of-network copays, some flagged as varying by site of care.
- **Accumulators are several EB=G lines**, split by Individual/Family, network,
  and Service Year / Year to Date / Remaining. The *remaining* figure is what
  actually caps exposure — here $3,805 of a $4,000 individual in-network max.

The 271 never says which tier a HCPCS code sits in — that is a formulary
lookup. So the Lines tab lets a user assign the tier, and a line without one
stays **unpriced** rather than being guessed at.

Worked example on her real benefits, Carboplatin + Paclitaxel:

| | In network | Out of network |
|---|---|---|
| Billed | $16,254 | $16,254 |
| Patient owes (est.) | **$440** | **$2,875** |
| Unpriced lines | 1 | 1 |

## API docs

FastAPI generates the OpenAPI spec from the code itself, so it cannot drift
from what the server does.

| URL | What it is |
|---|---|
| `http://localhost:8090/docs` | **Swagger UI** — every endpoint, expandable, with a working *Try it out* |
| `http://localhost:8090/redoc` | ReDoc — better for reading end to end |
| `http://localhost:8090/openapi.json` | The raw 3.1.0 spec — import into Postman/Insomnia or generate a client |

`docs/openapi.json` is a checked-in snapshot, so a spec change shows up in a diff.

47 schemas, 7 tag groups, 24 of 29 operations documenting a typed success
response. The five that don't are deliberate: an HTTP redirect (`/ontada/callback`),
three raw FHIR passthroughs whose shape is the server's not ours
(`/ontada/record`, `/everything`, `/resource/{type}`), and `/preauth/{id}/submit`,
which only ever returns 501.

Every non-2xx is the same envelope, documented on each operation:

```json
{ "error": { "code": "unconfigured", "message": "…", "detail": {} } }
```

**Careful with *Try it out*.** The configured Stedi key is a production key.
`POST /api/preauth/{id}/coverage` and `POST /api/casebooks/{id}/discover-coverage`
send real transactions to real payers about a real person, and may be billed.
The read-only `GET` endpoints are free.

## Payer-specific intake form

`app/payer/forms.py` (ported from `genesilico-preauth`) builds the field schema
for a payer: a Medicare MBI, a BlueCard alpha prefix, a TRICARE sponsor SSN and
a commercial member ID are not interchangeable, and sending the wrong one earns
an AAA rejection. Each field carries the X12 element it maps to, so the form and
the 270 it produces cannot drift apart.

- `GET  /api/eligibility/form?insurer=&payer_id=` — the schema the UI renders
- `POST /api/eligibility/run` — validate, then call the payer **or** replay a
  stored 271 (`replay` names a file; never silently on)
- `GET  /api/eligibility/replays` — stored responses available for replay

## Backend layout

```
backend/app/
  config.py            env-driven; a missing key disables a capability, never fakes it
  db.py                SQLAlchemy async — SQLite locally, Postgres by DATABASE_URL
  errors.py            one error envelope; upstream messages preserved verbatim
  cache.py             TTL cache with single-flight; Redis-shaped interface
  services/coverage.py         271 -> per-line cost estimates
  services/fhir_import.py      FHIR bundle -> casebook + coverage
  services/clinical_summary.py FHIR bundle -> clinical picture + gaps (deterministic)
  integrations/                stedi.py, ontada.py, x271.py  (ported from genesilico-preauth)
  routers/                     health, payers, eligibility, ontada, admin, casebooks, preauth
  connect_ontada.py            completes the SMART login from a pasted redirect URL
```

### Scaling notes

- `DATABASE_URL` is the only change needed to move to Postgres.
- `cache.py` is in-process. Behind replicas, back it with Redis.
- **`integrations/ontada.py` holds PKCE verifiers in process memory.** With more
  than one worker the OAuth callback can land on a process that never saw the
  authorize call. Move that to Redis before running replicas.
- Payer search is cached for an hour; eligibility never is.

## Credentials

`backend/.env` (gitignored) holds the Stedi key and the Ontada settings.

**The configured Stedi key is a production key.** It reaches real payers, real
transactions may be billed, and it only answers for real member IDs — Stedi's
published fixture identities return AAA errors against real payers. To develop
against fixtures instead, swap in the commented test key.

> **Never run an eligibility check on an Ontada sandbox patient.** "PatCert Pat
> zzAdult" with payer *zzAetna* and member *9876543* is not a real person. A
> production key sends that to a real payer, earns an AAA rejection, and may be
> billed for it. Use `GET /api/eligibility/replays` — a stored production 271 —
> to exercise the benefits logic for free, and keep live checks for real member
> IDs.

### Ontada client registration

The portal app is **MyCasebook**, client `adcca48b-…`, App Type **Provider**,
SMART 2.0.0. Two settings are load-bearing and easy to get wrong:

- **Client Type must be `Private (Symmetric)`.** Under `Public`, the portal
  greys out `offline_access` and will not let you tick it — the server refuses a
  long-lived refresh token to a client that cannot authenticate itself. Without
  it the connection dies every hour.
- **The portal does not issue the client secret.** You generate it and paste the
  same value into both the portal and `ONTADA_CLIENT_SECRET`. A mismatch shows
  up only at token exchange, as `invalid_client`.

`Private (Asymmetric)` needs a JWKS reachable over public HTTPS. No route serves
one today, so choosing it fails the exchange — the `Client JWKs URL` field
pointing at an ordinary web page returns HTML where the server expects keys.
# genesilico-ehr
