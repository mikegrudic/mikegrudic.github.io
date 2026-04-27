import requests, json

token = "08f9fb08ed023dbc30c3750934055a54eca73666"
headers = {"Authorization": f"Bearer {token}"}

r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=200&page=1", headers=headers)
print(r.status_code)
print(r.text[:500])


activities = []
page = 1
while True:
    print(page)
    r = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page=200&page={page}", headers=headers)
    batch = r.json()
    if not isinstance(batch, list) or len(batch) == 0:
        break
    activities.extend(batch)
    page += 1
    print(f"Page {page-1}: got {len(batch)} activities (total: {len(activities)})")

print(f"\nTotal activities: {len(activities)}")
for a in activities:
    dist_mi = a['distance'] * 0.000621371
    print(f"{a['id']} | {a['name']} | {a['type']} | {dist_mi:.1f} mi | {a.get('calories', 'N/A')} cal | {a.get('total_elevation_gain', 0):.0f}m gain")
