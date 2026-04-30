import requests, json, re, time, sys

# Exchange authorization code for access token
CODE = sys.argv[1] if len(sys.argv) > 1 else input("Paste auth code: ")

r = requests.post("https://www.strava.com/oauth/token", data={
    "client_id": "231555",
    "client_secret": "b542f8e5f9fe6a1801ef6620f70c39f5b3ec36c4",
    "code": CODE,
    "grant_type": "authorization_code",
})
token_data = r.json()

if "access_token" not in token_data:
    print("Failed to get access token:", token_data)
    exit(1)

print("Got access token")
token = token_data["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Fetch all activities
activities = []
page = 1
while True:
    r = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page=200&page={page}", headers=headers)
    batch = r.json()
    if not isinstance(batch, list) or len(batch) == 0:
        break
    activities.extend(batch)
    print(f"Page {page}: got {len(batch)} activities (total: {len(activities)})")
    page += 1

print(f"\nTotal activities: {len(activities)}")

# Filter: >= 2000ft (610m) gain OR >= 15mi distance, exclude VirtualRide
min_gain_m = 2000 * 0.3048
min_dist_m = 15 * 1609.34

filtered = []
for a in activities:
    if a['type'] == 'VirtualRide':
        continue
    if a.get('total_elevation_gain', 0) >= min_gain_m or a['distance'] >= min_dist_m:
        filtered.append(a)

print(f"{len(filtered)} activities match criteria\n")

# For each filtered activity, scrape the embed token from the activity page
session = requests.Session()
session.cookies.update({"_strava4_session": token})

embeds = []
for i, a in enumerate(filtered):
    dist_mi = a['distance'] * 0.000621371
    gain_ft = a.get('total_elevation_gain', 0) * 3.28084
    print(f"[{i+1}/{len(filtered)}] {a['id']} | {a['name']} | {dist_mi:.1f}mi | {gain_ft:.0f}ft ... ", end="", flush=True)

    resp = session.get(f"https://www.strava.com/activities/{a['id']}")
    # Look for the embed token in the page HTML
    match = re.search(r'data-token="([^"]+)"', resp.text)
    if not match:
        # Try alternate pattern
        match = re.search(r'"token":"([^"]+)"', resp.text)
    if match:
        embed_token = match.group(1)
        embeds.append((a['id'], embed_token))
        print(f"OK (token: {embed_token[:8]}...)")
    else:
        print("NO TOKEN FOUND")

    time.sleep(0.5)  # be nice to Strava

# Output the embed HTML sorted by activity ID descending (most recent first)
embeds.sort(key=lambda x: x[0], reverse=True)

print(f"\n\n=== EMBED HTML ({len(embeds)} activities) ===\n")
for aid, tok in embeds:
    print(f'\t\t\t\t\t\t\t<div class="strava-embed-placeholder" data-embed-type="activity" data-embed-id="{aid}" data-style="standard" data-from-embed="false" data-token="{tok}"></div>\n')
print('\t\t\t\t\t\t\t<script src="https://strava-embeds.com/embed.js"></script>')
