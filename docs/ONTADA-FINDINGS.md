# Ontada sandbox — what we can actually get

Measured 2026-09-09/10 against the live gateway. Everything below is from the
server's own responses, not documentation.

## Redirect URI — SOLVED 2026-09-12

The registered value was read out of the Ontada portal. App **"MyCasebook"**:

```
Launch URL:   https://canceros.genesilico.ai/
Redirect URL: https://canceros.genesilico.ai/     <- trailing slash is part of it
```

`ONTADA_REDIRECT_URI` is now set to exactly that. The authorize request clears
the Imperva WAF and reaches the authorization server. The earlier 403s were
entirely caused by loopback values in `redirect_uri`; re-confirmed on
2026-09-12 that `http://localhost:3045/...` still returns the Imperva
interstitial, so **loopback will never work and an https value is mandatory.**

That host is not this app — it serves an unrelated splash page, and genesilico-ehr
is not deployed anywhere. That does not matter. OAuth only needs the browser to
land there with `?code=...&state=...` in the address bar; `backend/connect_ontada.py`
lifts the pair out of a pasted URL and drives the local callback, so no hosting
and no new app registration is needed to complete a login.

## CONNECTED 2026-09-13 — what is actually in there

Signed in as `practitioner-aakash@genesilico.ai`. Live token, refresh token
held, provider-scoped `user/*` read across the whole panel.

```
fhirUser        Practitioner/0481e0c1-8855-4e56-920a-4d12ab7fa8a0  ("Aakash G")
patient context none (deliberate — see the resolver loop below)
```

### The sandbox is NOT empty — earlier guess was wrong

The `test-ui_smoke` tenant name suggested a bare store. Measured counts say
otherwise:

| Resource | Count | | Resource | Count |
|---|---|---|---|---|
| Patient | **224** | | Encounter | 912 |
| Observation | 2245 | | DiagnosticReport | 383 |
| MedicationRequest | 2025 | | DocumentReference | 333 |
| MedicationAdministration | 225 | | Procedure | 196 |
| Condition | 110 | | Specimen | 59 |
| MedicationStatement | 48 | | CarePlan | 42 |
| Immunization | 35 | | AllergyIntolerance | 27 |
| CareTeam | 24 | | **Coverage** | **23** |

### The one patient worth building against

`Patient/EAAB756F4ECC462DB72ACDF47546F912` — "PatCert Pat zzAdult", MR
`certadult`, male, DOB 1990-01-01. The name and MR mark it as Ontada's ONC
**(g)(10) certification** patient, which is why it is the only fully populated
one. A near-identical duplicate exists at `Patient/21454`; the two differ only
in city ("Tampa" vs "Tampa Bay"), so pick one and stay on it.

It is a genuine colorectal oncology chart:

- **Conditions** — Primary malignant neoplasm of rectum (SNOMED 93984006),
  primary malignant neoplasm of colon (93761005), rectal haemorrhage
  (12063002), plus food insecurity (733423003) as an SDOH finding.
- **Medications** — **Cetuximab IV ×6**, Granisetron IV ×2, Dexamethasone and
  Prednisone oral, Acetaminophen (draft).
- 86 Observations, 35 DocumentReferences, 22 DiagnosticReports, 31 Encounters.

Cetuximab for colorectal cancer is precisely a prior-auth case, so this patient
exercises the real workflow rather than a toy one.

### Coverage: the prize, and it is populated

Two of the 23 Coverage resources carry everything the 270 needs:

```
Coverage/preG2API.826139.  active     Patient/EAAB756F...  memberId 123456
                                      plan 765432   group 345678
Coverage/preG2API.826228.  cancelled  Patient/EAAB756F...  memberId 876543
                                      plan 01837373 group 01837372
```

Member ID, plan and group all present — the fields staff retype by hand today.
Note one is `cancelled`: good, the import must filter on `status = active`
rather than taking the first hit. The other 19 Coverage rows have no
beneficiary reference and no payor at all, so they are unusable stubs — the
mapper must treat a Coverage without a resolvable `beneficiary` as absent.

### Two populations of Patient, only one clinical

Searching `/Patient` returns two clearly different shapes:

- **UUID ids** with a `https://interopio.ontada.com/portal/user-id`
  identifier, no gender, no DOB — these are *portal login accounts*, not
  charts. `patient-aakash@genesilico.ai` is one of them:
  `Patient/3bc1d8cb-c632-4c52-a78c-35e347d13bad`, name "Aakash G", an email and
  nothing else. **There is no clinical record behind the patient test login.**
- **Uppercase-hex or numeric ids** with an `MR` identifier, gender and DOB —
  the real iKnowMed-shaped records (Frankie Craven, Laurie A Baff, Harry
  Smithey, Louie Barker, Linda Bluebell, CAROL1 A LOGAN, plus the certification
  patient). One Synthea import is also present.

So a patient-picker must not list everything `/Patient` returns. Filter on the
presence of an `MR` identifier, or those 200-odd login accounts drown the real
charts.

### ⚠️ Stored XSS payload in the patient list

One record's name is literally:

```
adk<a href=attacker.com>cezeri was here</a> bdk<a href=...>cezeri was here</a>
```

Someone has left an XSS probe in the sandbox. It is harmless as data, but it is
a live test of whether our UI escapes what it renders. **Any screen that prints
a patient name must escape it.** React escapes by default; the risk is anywhere
we reach for `dangerouslySetInnerHTML`, build HTML by string concatenation, or
render a name into a PDF or email template. Worth a deliberate check before any
demo that lists patients.

## Files — the actual documents, 2026-09-13

`DocumentReference.content.attachment` and `DiagnosticReport.presentedForm`
carry no inline `data` and no `size`, only a relative `url` of the form
`Binary/<id>`. The bytes need a second fetch.

**Binary is readable.** `GET /Binary/<id>` returns 200 with a FHIR `Binary`
resource carrying base64 `data` — and it returns that *whatever* Accept header
is sent. `Accept: application/pdf` still comes back
`application/fhir+json`, so the content type must be read from the resource's
own `contentType` field, never from the HTTP response header. Decoded samples
verified as a real 1-page `%PDF-1.5` and a real 950×1324 `\x89PNG`.

Binary was NOT in the scope the token was granted (`user/Binary.r` is granted by
the registration but the authorize request had not asked for it) and the read
succeeded anyway — the gateway is not enforcing it. `ONTADA_SCOPES` now requests
it properly rather than relying on that.

### 44 referenced, 34 retrievable

| | |
|---|---|
| Attachments referenced | 44 (17 PDF, 17 PNG, 8 JPEG, 2 XML) |
| Actually retrievable | **34** |
| Dangling references | **10** |

A dangling one answers `404 HAPI-2001: Resource Binary/<id> is not known`. The
chart references a file the store does not hold. **The id prefix predicts it
perfectly in this dataset:** every retrievable attachment is `Binary/pre…`,
every dangling one is `Binary/FA…`. Ten of them, no exceptions either way.

That is a property of this sandbox, not a rule to code against — but it is worth
knowing, because it means a "documents on file" count taken from
DocumentReference alone **overstates the evidence available by 23%**. Anything
that promises a payer an attachment must confirm the fetch, not the reference.

Handled rather than hidden: `GET /api/ontada/file/{id}` returns **404
`attachment_missing`** with that explanation, not a 502, because the EHR
answered correctly — it simply has no such file. The list field is named
`addressable` (we have a handle to try), never `available`.

## The scope grant, and three traps in it

The registration was widened in the portal on 2026-09-12. Getting a working
request out of it took three corrections, each measured rather than guessed:

1. **`offline_access` is only available to a confidential client.** It is
   greyed out and unclickable while Client Type is `Public` — the server
   refusing a long-lived refresh token to a client that cannot authenticate
   itself. Fixed by moving to **Private (Symmetric)**. Note the portal does not
   *issue* the secret; you generate it and paste the same value both sides.
2. **`launch/patient` must NOT be requested.** It hands the browser to Ontada's
   own `smart_context_resolver`, which on 2026-09-13 redirected to itself
   accumulating one `launch=<uuid>` per hop until the browser aborted at ~20
   with "too many redirects". That loop is inside *their* client, not ours.
   Dropping the scope sends the login straight to the provider portal. The
   consequence is no patient context — which costs nothing, because `user/*`
   reads the whole panel and pre-auth staff need to *search* anyway.
3. **`launch` must not be requested either** (needs an in-EHR launch token),
   and **Binary is granted `.r` only**, not `.rs`.

A rejection is whole-request: asking for one ungranted scope loses everything,
so `ONTADA_SCOPES` pins the exact verified string.

## Redirect URI, and why the code kept vanishing

Registered value, app "MyCasebook": `https://canceros.genesilico.ai/` —
trailing slash included, matched literally. Loopback is refused by Ontada's
Imperva WAF before OAuth runs, re-confirmed 2026-09-12, so an https value is
mandatory and local development cannot use `localhost`.

That host is an unrelated Next.js app, and genesilico-ehr is not deployed
anywhere. That does not matter for OAuth — but its client-side router
immediately navigates `/` → `/auth/login`, **wiping `?code=` before it can be
copied**. The code *is* delivered (every path returns 200 with the query
intact server-side); the browser throws it away a moment later.

Fixes, either works:
- Register a path the site 404s on, e.g. `/oauth/callback`. A not-found page
  runs no router, so the address bar keeps the code. The portal accepts several
  redirect URLs separated by `;`.
- Or recover it from browser history / DevTools with *Preserve log* ticked.

`backend/connect_ontada.py` completes the login from a pasted URL, so no
hosting and no new app registration is needed.

## What the gateway exposes

`GET /metadata` returns a **HAPI FHIR Server 8.8.1** CapabilityStatement,
FHIR R4 (4.0.1), advertising **146 resource types** with full
`read / vread / search / create / update / patch / delete / history`.

Treat that number with suspicion. It is the generic HAPI statement for the
underlying store, not a curated iKnowMed API surface. **146 types advertised is
not 146 types with oncology data in them.**

Two operations do matter:

- **`Patient/$everything`** — pulls the whole chart in one paged call. Now
  implemented as `GET /api/ontada/everything`; far cheaper than walking each
  resource type.
- **`Observation/$lastn`** — most-recent-N labs per code, which is exactly the
  shape a completeness check wants (latest creatinine, latest ECOG).

## The sandbox is a smoke-test store, not an iKnowMed chart

The `OperationDefinition` URLs in the CapabilityStatement leak the backing
store:

```
io-in.prod.west.ontada.mckesson.com/cdr-v3/fhir-r4/fhir/test-ui_smoke-70406015_cdr-70406068/
```

That tenant is named **`test-ui_smoke`** — a UI smoke-test Clinical Data
Repository. Server-level operations are stock HAPI admin
(`expunge`, `perform-reindexing-pass`, `mark-all-resources-for-reindexing`).

Read plainly: this is a vanilla HAPI CDR behind the InteropiO gateway, not a
populated iKnowMed G2 instance. Expect a thin synthetic patient, not a real
oncology chart. `$get-resource-counts` would settle exactly how thin, and it is
one authenticated call away once the redirect URI is fixed.

## What we could build once authenticated

Ranked by what the pre-auth workflow actually needs.

**Directly useful**

| Resource | What it gives the product |
|---|---|
| `Patient` | Demographics, MRN — the identity a payer matches on |
| `Coverage` | Payer, member ID, group number → **feeds the 270 directly**, removing the most error-prone manual step |
| `Condition` | Diagnosis + ICD-10 → the medical-necessity codes on the package |
| `MedicationRequest` / `MedicationAdministration` | Prior lines of therapy, and the drugs to price by tier |
| `Observation` | Labs, ECOG, staging values → the completeness check |
| `DocumentReference` | Pathology, imaging, consult notes → package evidence |
| `Encounter` | Place of service, which changes the payer's copay tier |

**Interesting, unproven**

The gateway advertises `Claim`, `CoverageEligibilityRequest`,
`CoverageEligibilityResponse` and `ExplanationOfBenefit`. It advertises `create`
on all of them. That does **not** give us prior authorisation — Da Vinci PAS
needs `Claim/$submit`, which is *not* in the operation list. But it is the first
sign of an auth-adjacent path anywhere in this stack, and worth asking Ontada
about directly.

## What this changes about the product

**The Coverage resource is the prize.** Today someone types the payer, member ID
and group number into the pre-auth form by hand, and a typo returns an AAA
rejection from the payer. Pulling `Coverage` makes that automatic and correct.
That single link is worth more than the rest of the FHIR surface combined.

**Do not plan on the sandbox for clinical realism.** Build and demo the clinical
screens against real casebook data; use Ontada to prove the *connection*, not to
supply a convincing patient.

## Also tried: reading the redirect URI out of the console

The registered value is visible in the InteropiO console, so I tried to read it.

- The console needs an **account ID**, which the FHIR base URL encodes:
  `/gateway/fhir/`**`developerportalio`**`/portal/gw-fhir`. That resolved
  correctly to `developerportalio.interopio.ontada.com`.
- Both sandbox accounts were rejected there with **"Incorrect credentials"**.
  The email step advanced but the password failed.

So `patient-aakash@` and `practitioner-aakash@` are **FHIR sandbox users, not
developer-portal console users**. Reading the redirect URI needs the portal
login that owns the app registration. I stopped after one attempt per account
rather than risk a lockout.

## One-call import — now exercised against real data

`POST /api/ontada/import?patient_id=` does the whole thing: `$everything` → map
→ casebook, plus a pre-auth package when the bundle carries a usable `Coverage`.
Run against the certification patient it produced casebook `cb-0ac753e3` and
package `pa-fe2dba7c` (zzAetna, member 9876543, group 345678).

`services/fhir_import.py` holds the mapping. It is deliberately conservative: a
field the bundle does not carry stays empty and is listed in `unmapped`. The
first run against REAL data corrected four defects the hand-written test bundles
had never exposed, each now covered by a regression test (9 passing):

| Field | Was | Cause |
|---|---|---|
| Primary diagnosis | "Food insecurity" | An SDOH finding recorded in 2025 outranked the 2022 colon cancer on recency; every other scoring term tied |
| Diagnosis code | SNOMED `93761005` | The ICD-10 constant was `.../sid/icd-10-cm`; Ontada emits `.../sid/icd-10`, so nothing matched and it silently fell back |
| Payer name | *(empty)* | Ontada puts the payor Organization in `Coverage.contained`; the mapper only looked outside the resource |
| Plan number | *(unmapped)* | Only `group` was read from `Coverage.class` |

A fifth, in the document tally: 10 of 35 DocumentReferences are typed with an
HL7 **NullFlavor** code whose display string is "Unknown" — which reads like a
real category and collapsed them into one bucket. They now fall back to their
US Core category.

## Immediate next steps

1. **Wire the chart into the package.** The regimen carries RxNorm codes for the
   Lines tab, and the 34 retrievable files are what would attach as evidence.
2. **Add a patient picker to the UI.** The connect page's buttons still call
   `/record` and `/import` without a `patient_id` and now return a clear 400.
   Filter the picker on the presence of an `MR` identifier — see the two
   populations above.
3. **Audit name rendering for XSS** before any demo that lists patients.
4. **Ask Ontada about the `smart_context_resolver` loop.** It is their bug, and
   an in-EHR launch is not possible while it persists. The authorize URL from
   2026-09-13 is the reproduction.
5. Prior-auth submission remains blocked on a 278 path — unchanged by any of
   this, and not something Ontada can solve.
