import requests, json

token = "08f9fb08ed023dbc30c3750934055a54eca73666"
headers = {"Authorization": f"Bearer {token}"}

activities = []
page = 1
while True:
    r = requests.get(f"https://api.strava.com/api/v3/athlete/activities?per_page=200&page={page}", headers=headers)
    batch = r.json()
    if not batch:
        break
    activities.extend(batch)
    page += 1

print(f"Total activities: {len(activities)}")
for a in activities:
    dist_mi = a['distance'] * 0.000621371
    print(f"{a['id']} | {a['name']} | {a['type']} | {dist_mi:.1f} mi | {a.get('calories', 'N/A')} cal | {a.get('total_elevation_gain', 0):.0f}m gain")
