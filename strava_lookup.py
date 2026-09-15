"""Add Strava activity embeds to the feed in adventures.html.

Activities after roughly mid-2025 will not render unless the embed div
carries a data-token; older ones are grandfathered and work bare. Getting a
token requires being logged in to Strava, so pass a session cookie or supply
the tokens yourself.

  python strava_lookup.py --add 12345 67890 --session <_strava4_session>
      Look up each activity's embed token using a logged-in session cookie,
      then insert. Copy the cookie value from browser dev tools (F12):
      Firefox uses Storage -> Cookies -> https://www.strava.com, Chrome uses
      Application -> Cookies. The row is named _strava4_session.

  python strava_lookup.py --auto --session <_strava4_session>
      Find every new non-virtual activity above MIN_GAIN_FT in the training
      log, mint its embed token, and add it. This is the usual way to
      refresh the page.

  python strava_lookup.py --paste snippets.txt      (or: ... --paste - )
      Read embed snippets copied from each activity's Share -> Embed
      dialog and insert them. Accepts the placeholder-div or iframe form,
      any number of them, with surrounding junk. Needs no credentials.

  python strava_lookup.py --add 12345:TOKEN 67890:TOKEN
      Insert with tokens supplied directly.

  python strava_lookup.py
      Pull everything above MIN_GAIN_FT straight from the Strava API. Needs
      API access, which Strava restricts to paid subscribers; the first run
      needs an auth code (see AUTH_URL), and the refresh token is then
      cached in strava_tokens.json (gitignored).

IDs already in the page are skipped, so reruns are safe.
"""
import requests, json, re, sys, os, time

CLIENT_ID = "231555"
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET", "")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(REPO_DIR, "strava_tokens.json")
HTML_FILE = os.path.join(REPO_DIR, "adventures.html")

MIN_GAIN_FT = 2000
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
AUTH_URL = (f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
            "&response_type=code&redirect_uri=http://localhost"
            "&approval_prompt=force&scope=activity:read_all")


def existing_ids(html):
    return set(map(int, re.findall(r'data-embed-id="(\d+)"', html)))


def embed_div(aid, tok):
    tok_attr = f' data-token="{tok}"' if tok else ""
    return ('\t' * 7 + '<div class="strava-embed-placeholder" '
            f'data-embed-type="activity" data-embed-id="{aid}" '
            f'data-style="standard" data-from-embed="false"{tok_attr}></div>')


def insert(html, entries):
    """Place each embed above the first existing one with a lower id.

    Activity ids increase over time, so this keeps the feed newest-first
    whether entries arrive in one batch or a few at a time. Existing lines
    are never reordered.
    """
    lines = html.split("\n")
    for aid, tok in sorted(entries):
        at = next((i for i, ln in enumerate(lines)
                   if (m := re.search(r'data-embed-id="(\d+)"', ln))
                   and int(m.group(1)) < aid), None)
        if at is None:  # older than everything present; go below the last one
            at = max(i for i, ln in enumerate(lines)
                     if "strava-embed-placeholder" in ln) + 1
        lines.insert(at, embed_div(aid, tok))
    return "\n".join(lines)


def parse_snippets(text):
    """Pull (id, token) pairs out of embed snippets copied from Strava.

    Handles the placeholder-div and iframe forms the Share dialog offers,
    with the id and token in either order.
    """
    pairs = {}
    patterns = [
        r'data-embed-id="(\d+)"[^>]*?data-token="([\w\-]+)"',
        r'data-token="([\w\-]+)"[^>]*?data-embed-id="(\d+)"',
        r'activity/(\d+)\?token=([\w\-]+)',
    ]
    for i, pat in enumerate(patterns):
        for a, b in re.findall(pat, text):
            aid, tok = (b, a) if i == 1 else (a, b)
            pairs[aid] = tok
    # bare ids with no token at all still get a shot at rendering
    for aid in re.findall(r'data-embed-id="(\d+)"', text):
        pairs.setdefault(aid, None)
    return sorted(pairs.items(), reverse=True)


def list_recent(session, newest, max_pages=10):
    """Return qualifying activities newer than `newest`, via the training log.

    The public API is subscriber-only now, so this reads the same JSON the
    logged-in training log page uses. Ids increase over time, so paging can
    stop once a page reaches back past what is already embedded.
    """
    found, page = [], 1
    while page <= max_pages:
        r = session.get("https://www.strava.com/athlete/training_activities",
                        params={"keywords": "", "activity_type": "", "workout_type": "",
                                "commute": "", "new_activity_only": "false",
                                "page": page, "per_page": 20},
                        headers={"X-Requested-With": "XMLHttpRequest",
                                 "Referer": "https://www.strava.com/athlete/training"},
                        timeout=45)
        try:
            models = r.json().get("models", [])
        except ValueError:
            sys.exit("Could not read the training log -- cookie expired?")
        if not models:
            break
        for a in models:
            if a["id"] <= newest:
                continue
            gain_ft = a.get("elevation_gain_raw", 0) * 3.28084
            if gain_ft > MIN_GAIN_FT and not a["sport_type"].startswith("Virtual"):
                found.append(a)
                print(f"  {a['id']}  {a['start_date']:16} {gain_ft:6.0f}ft  {a['name'][:40]}")
        if min(a["id"] for a in models) <= newest:
            break
        page += 1
        time.sleep(0.4)
    else:
        print(f"  (stopped at {max_pages} pages; rerun if more are missing)")
    return found


def csrf_token(aid, session):
    """Fetch an activity page for its CSRF token, confirming the session works."""
    r = session.get(f"https://www.strava.com/activities/{aid}", timeout=45)
    m = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
    if not m or not re.search(r'log ?out|athlete-menu', r.text, re.I):
        sys.exit("Session cookie is not logged in -- grab a fresh "
                 "_strava4_session from browser dev tools.")
    return m.group(1)


def mint_token(aid, session, csrf):
    """Ask Strava's share endpoint for an activity's embed token.

    This is the private call the Share -> Embed dialog makes; the token no
    longer appears in the activity page HTML. Expect it to change without
    warning, in which case fall back to --paste.
    """
    r = session.post("https://www.strava.com/api/next/sharing/prepare-entity",
                     json={"embedType": "Activity", "embedId": str(aid)},
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json, text/plain, */*",
                              "x-csrf-token": csrf,
                              "X-Requested-With": "XMLHttpRequest",
                              "Referer": f"https://www.strava.com/activities/{aid}",
                              "Origin": "https://www.strava.com"}, timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    tok = r.json().get("token")
    return (tok, "ok") if tok else (None, "no token in response")


def verify(aid, tok):
    """Confirm the embed actually renders: 200 = good, 403 = token needed."""
    url = f"https://strava-embeds.com/activity/{aid}"
    if tok:
        url += f"?token={tok}"
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=45).status_code
    except Exception:
        return None


def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            grant = {"grant_type": "refresh_token",
                     "refresh_token": json.load(f)["refresh_token"]}
    elif len(sys.argv) > 1:
        grant = {"grant_type": "authorization_code", "code": sys.argv[1]}
    else:
        sys.exit(f"No stored token. Authorize at:\n{AUTH_URL}\n"
                 "then rerun with the code from the redirect URL.")
    if not CLIENT_SECRET:
        sys.exit("Set STRAVA_CLIENT_SECRET in the environment.")
    data = requests.post("https://www.strava.com/oauth/token",
                         data={"client_id": CLIENT_ID,
                               "client_secret": CLIENT_SECRET, **grant}).json()
    if "access_token" not in data:
        sys.exit(f"Token request failed: {data}")
    with open(TOKEN_FILE, "w") as f:
        json.dump({"refresh_token": data["refresh_token"]}, f)
    return data["access_token"]


def fetch_activities(token):
    headers = {"Authorization": f"Bearer {token}"}
    activities, page = [], 1
    while True:
        batch = requests.get("https://www.strava.com/api/v3/athlete/activities"
                             f"?per_page=200&page={page}", headers=headers).json()
        if not isinstance(batch, list):
            sys.exit(f"Activities request failed: {batch}\n"
                     "A 403 'Application Inactive' means API access is off; "
                     "use --add instead.")
        if not batch:
            return activities
        activities.extend(batch)
        page += 1


def parse_args():
    argv = sys.argv[1:]
    cookie = None
    if "--session" in argv:
        i = argv.index("--session")
        cookie = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    return argv, cookie


def main():
    argv, cookie = parse_args()
    with open(HTML_FILE) as f:
        html = f.read()
    have = existing_ids(html)
    print(f"{len(have)} activities already embedded")

    session = None
    if cookie:
        session = requests.Session()
        session.headers.update({"User-Agent": UA})
        session.cookies.set("_strava4_session", cookie, domain=".strava.com")

    if argv and argv[0] == "--paste":
        blob = sys.stdin.read() if argv[1:] in ([], ["-"]) else open(argv[1]).read()
        entries = [(aid, tok) for aid, tok in parse_snippets(blob)
                   if int(aid) not in have]
        entries = [(int(a), t) for a, t in entries]
        if not entries:
            sys.exit("No new id/token pairs found in the pasted text.")
    elif argv and argv[0] == "--add":
        entries = []
        for arg in argv[1:]:
            # accepts a bare id, an activity URL, or either suffixed with :TOKEN
            m = re.search(r"(\d{6,})(?::([\w\-]+))?\s*$", arg)
            if not m:
                sys.exit(f"Cannot parse activity from {arg!r}")
            aid = int(m.group(1))
            if aid not in have:
                entries.append((aid, m.group(2)))
        if not entries:
            sys.exit("Nothing to add (all IDs already present).")
    elif argv and argv[0] == "--auto":
        if not cookie:
            sys.exit("--auto needs --session <_strava4_session>.")
        entries = [(a["id"], None) for a in list_recent(session, max(have))]
        if not entries:
            print("No new activities match criteria")
            return
    else:
        activities = fetch_activities(get_token())
        print(f"Fetched {len(activities)} activities")
        entries = [(a["id"], None) for a in activities
                   if a["id"] not in have
                   and not a["type"].startswith("Virtual")
                   and a.get("total_elevation_gain", 0) * 3.28084 > MIN_GAIN_FT]
        if not entries:
            print("No new activities match criteria")
            return

    if cookie:
        csrf = csrf_token(entries[0][0], session)
        resolved = []
        for i, (aid, tok) in enumerate(entries, 1):
            if tok:
                resolved.append((aid, tok))
                continue
            tok, why = mint_token(aid, session, csrf)
            print(f"  [{i}/{len(entries)}] {aid}: {why}")
            resolved.append((aid, tok))
            time.sleep(0.5)
        entries = resolved

    print("verifying embeds render...")
    bad = []
    for aid, tok in entries:
        code = verify(aid, tok)
        if code != 200:
            bad.append((aid, code))
        time.sleep(0.5)
    if bad:
        print("\nThese will NOT render and were not added:")
        for aid, code in bad:
            hint = "token missing/invalid" if code == 403 else f"HTTP {code}"
            print(f"  {aid}: {hint}")
        entries = [e for e in entries if e[0] not in {b[0] for b in bad}]
    if not entries:
        sys.exit("\nNothing renderable to add.")

    with open(HTML_FILE, "w") as f:
        f.write(insert(html, entries))
    added = sorted((a for a, _ in entries), reverse=True)
    print(f"\nAdded {len(entries)} embeds: {added}")


if __name__ == "__main__":
    main()
