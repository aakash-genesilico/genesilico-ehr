#!/usr/bin/env python3
"""Complete the Ontada SMART login when the registered redirect URI points at a
page that cannot receive the code itself (an unhosted app, a splash screen).

OAuth puts `?code=...&state=...` in the browser's address bar regardless of what
that page renders. This lifts the pair out of the pasted URL and hands it to the
local callback, which does the real token exchange and stores the tokens.

    ./.venv/bin/python connect_ontada.py            # step 1: print login URL
    ./.venv/bin/python connect_ontada.py '<url>'    # step 2: paste where you landed

The backend must stay running between the two steps: the PKCE verifier lives in
process memory (integrations/ontada.py:_PENDING) and dies with the process.
"""
import sys, urllib.parse, httpx

API = "http://localhost:8090/api"

def die(msg): sys.exit(f"\n  {msg}\n")

if len(sys.argv) < 2:
    r = httpx.get(f"{API}/ontada/authorize", timeout=30)
    if r.status_code != 200: die(f"authorize failed: {r.status_code} {r.text[:300]}")
    print("\nOpen this in a REAL browser tab (curl gets a 403 from the WAF),")
    print("sign in as the sandbox patient, and approve:\n")
    print(r.json()["url"])
    print("\nYou will land on your splash page. Copy the WHOLE address bar and run:")
    print("  ./.venv/bin/python connect_ontada.py '<paste>'\n")
    print("The code is short-lived — do it straight away.\n")
    sys.exit(0)

q = urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[1]).query)
if "error" in q:
    die(f"Ontada refused the login: {q['error'][0]} — {q.get('error_description',[''])[0]}")
code, state = q.get("code", [None])[0], q.get("state", [None])[0]
if not code or not state:
    die("That URL has no ?code= and ?state=. Either the login did not finish, or "
        "the splash page dropped the query string (then it needs a page that keeps it).")

r = httpx.get(f"{API}/ontada/callback", params={"code": code, "state": state},
              timeout=60, follow_redirects=False)
loc = r.headers.get("location", "")
if "ontada_error" in loc:
    die("Exchange failed: " + urllib.parse.unquote(loc.split("ontada_error=", 1)[1]))
if "ontada_connected" not in loc and r.status_code >= 400:
    die(f"Callback returned {r.status_code}: {r.text[:400]}")

s = httpx.get(f"{API}/ontada/status", timeout=30).json()
print("\nConnected." if s.get("connected") else "\nCallback returned but status says not connected:")
print(f"  fhirUser        : {s.get('fhir_user') or '(no id_token claim)'}")
print(f"  scopes granted  : {s.get('scope') or '(not reported)'}")
print(f"  patient context : {s.get('patient_context') or '(none — expected on an SSO-only grant)'}")
print(f"  refresh token   : {'yes' if s.get('can_refresh') else 'no (offline_access is not granted)'}")
print("""
fhirUser is the whole prize here: it names the FHIR resource behind the login,
so Practitioner/... vs Patient/... tells us what these sandbox accounts really
are. Reading that resource still needs a scope Ontada has not granted.
""")
