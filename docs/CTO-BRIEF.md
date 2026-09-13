# GeneSilico EHR module — brief for the CTO

Updated 9 September 2026, after the backend was built and both integrations
were tested against live endpoints.

---

## 1. One line

A module that connects **Texas Oncology's EHR (Ontada iKnowMed)** to our
iCaseBook, and prices a patient's planned treatment against their **real
insurance benefits** before treatment starts.

## 2. The problem

**Gap 1 — we cannot read their data.** Texas Oncology's charts sit in Ontada
iKnowMed. gSage has no connection. Today someone re-types the history by hand.

**Gap 2 — pre-auth is manual.** In the US the hospital must get the insurer's
approval before an expensive treatment. Done wrongly, either the hospital is not
paid or the patient gets a shock bill. Staff currently do this by phone and fax
over several days.

## 3. Where it sits

Steps 4–6 (CancerAI, Digital Twin, doctor sign-off) are already in production in
gSage. This module builds the two ends: pulling the record in, and the
pre-auth work at the other end.

## 4. What is built now

**Frontend** — 11 screens, Next.js, same design system as gSage (Tailwind config
copied, not forked).

**Backend** — FastAPI, async SQLAlchemy, SQLite locally and Postgres by changing
one environment variable. Real Stedi and Ontada clients, TTL caching, one error
envelope, capability reporting.

**No mock data anywhere.** Fixtures are deleted. The database seeds only the
cancer center and its two facilities — tenant configuration, not clinical data.
Casebooks and packages start empty.

## 5. What we verified live — this is the important section

| Capability | Result |
|---|---|
| Stedi payer directory | **Works.** Real payer IDs. |
| Stedi eligibility 270/271 | **Works.** Our key is a **production** key — it reached the real UnitedHealthcare. |
| Stedi claim status, insurance discovery | **Work**, but only on the production key. |
| Ontada FHIR gateway | **Live.** Real CapabilityStatement and SMART config. |
| **Stedi prior auth (X12 278)** | **Does not exist.** |

### Three findings that change the plan

**1. We cannot submit a prior authorisation.** Stedi has no 278 endpoint. Every
candidate path returns 404 on both our test and production keys. This is the
single biggest constraint on the product. The submit endpoint deliberately
returns 501 with the reason rather than inventing an authorisation number.

*Decision needed:* a clearinghouse that carries 278 (Availity, Change
Healthcare, Waystar), the payer's own portal, or Da Vinci PAS where offered.

**2. Ontada cannot be accessed server-to-server.** The gateway supports
`authorization_code` only — no `client_credentials`. A human must sign in through
a browser once; the refresh token then keeps the backend running unattended.
Workable, but it means unattended overnight syncing needs someone to have
authorised first.

**3. RESOLVED — the registration is provider-scoped and we are connected.**
Superseded 13 Sep 2026. The registration was widened in the Ontada portal to
`user/*` read scopes plus `offline_access`, and we now sign in as a practitioner
and read a **224-patient panel**. No new registration was needed from Ontada.

What remains, and it is theirs not ours: requesting `launch/patient` sends the
browser into Ontada's own `smart_context_resolver`, which loops until the
browser aborts. So an **in-EHR launch is not possible** — a clinician cannot
open a patient in iKnowMed and click through to us. Standalone launch plus our
own patient search works, and for pre-auth that is the better shape anyway,
since staff need to *find* a patient rather than be handed one.

*Decision needed:* whether to raise the resolver loop with Ontada now, or accept
standalone-only launch for the first release.

## 6. What is honest about the money screen

A 271 tells you the **benefit** — active/inactive, deductible, out-of-pocket max,
coinsurance, copay. It does **not** adjudicate a specific drug code. So the
system separates *payer-stated* facts from *our estimate*, labels the estimate,
and never marks a line "denied". Unknown stays unknown.

Verified working: against a real Aetna benefit response, a 0% coinsurance drug
line priced at $0 and a $25 copay applied once to the encounter line.

## 7. Two things to be careful about

**The configured Stedi key is production.** Real transactions may be billed and
it queries real payers about real people. A test key is available and commented
in the env file for development.

**HIPAA applies the moment real patient data flows.** BAA, encryption, audit
logging on every record access, role-based access. None of it is in place — the
backend currently has no authentication at all. This must be built before the
first real patient.

## 8. Decisions I need

1. Which clearinghouse for the 278, and who signs it?
2. Do we raise the `smart_context_resolver` loop with Ontada, or ship
   standalone-launch-only? (An in-EHR launch is blocked until they fix it.)
3. Do we build auth + audit into this module now, or inherit it from gSage?
4. Test key or production key as the default for the team?

## 9. Demo flow

Admin → Connections (shows live capability detection, including the 278 gap) →
Connect (real SMART login) → Casebooks → Pre-Auth: create a package, hit **Run
coverage check**, and watch a real 270 go to a real payer and come back priced.

Finish on the Submission tab, press submit, and let it explain why it refuses.
That refusal is the most valuable thing in the demo — it is the difference
between a system you can trust with a patient's bill and one you cannot.
