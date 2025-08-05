import os
import requests
import time
from datetime import datetime, timedelta

API_KEY = os.getenv("JUMPCLOUD_API_KEY")
BASE_URL = "https://console.jumpcloud.com/api"

if not API_KEY:
    print("❌ API key not loaded. Please add 'JUMPCLOUD_API_KEY' as a GitHub Secret.")
    exit(1)
else:
    print("🔐 API key loaded successfully.")

session = requests.Session()
session.headers.update({
    "x-api-key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
})


def get_all(endpoint, use_v2=False):
    results = []
    limit = 100
    skip = 0
    seen_pages = set()

    while True:
        prefix = "/v2" if use_v2 else ""
        url = f"{BASE_URL}{prefix}/{endpoint}?limit={limit}&skip={skip}"
        print(f"🌐 Requesting: {url}")
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            items = data.get("results", data)

            page_fingerprint = str(items)
            if not items or page_fingerprint in seen_pages:
                print("🛑 No new data or duplicate page detected. Stopping pagination.")
                break

            seen_pages.add(page_fingerprint)
            results.extend(items)
            skip += limit
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            break
    return results


def get_bound_users(system_id):
    url = f"{BASE_URL}/v2/systems/{system_id}/associations?type=user"
    try:
        res = session.get(url)
        res.raise_for_status()
        return res.json()
    except Exception:
        return []


def unbind_user(system_id, user_id):
    url = f"{BASE_URL}/v2/systems/{system_id}/associations"
    payload = {
        "op": "remove",
        "type": "user",
        "id": user_id
    }
    res = session.post(url, json=payload)
    print(f"🧹 Unbinding system {system_id} from user {user_id} — Status: {res.status_code}")
    return res.ok


def bind_user(system_id, user_id):
    url = f"{BASE_URL}/v2/systems/{system_id}/associations"
    payload = {
        "op": "add",
        "type": "user",
        "id": user_id
    }
    res = session.post(url, json=payload)
    print(f"📡 Attempting to bind system {system_id} to user {user_id}")
    print(f"➡️ Status Code: {res.status_code}")

    if res.status_code == 409:
        print("⚠️ Already bound — forcing rebind.")
        unbind_user(system_id, user_id)
        print("🔁 Rebinding...")
        res = session.post(url, json=payload)
        print(f"➡️ Rebind Status: {res.status_code}")
        if res.status_code < 300:
            print("✅ Rebind successful and should now show in UI.")
        else:
            try:
                print(f"❌ Rebind failed: {res.json()}")
            except Exception:
                print(f"❌ Rebind failed: {res.text}")
    elif res.status_code < 300:
        print("✅ Bound successfully!")
    else:
        try:
            print(f"❌ Failed to bind: {res.json()}")
        except Exception:
            print(f"❌ Failed to bind: {res.text}")

    return res.ok


def was_created_within_last_24_hours(timestamp):
    if not timestamp:
        return False
    try:
        created_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        created_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    return datetime.utcnow() - created_time <= timedelta(hours=24)


def normalize_hostname(name):
    return name.replace("WIN-", "").replace("-", "").replace("_", "").lower()


def main():
    start_time = time.time()
    print("🚀 Starting JumpCloud auto-binder...")

    users = get_all("systemusers")
    print(f"👥 Total users: {len(users)}")

    systems = get_all("systems")
    print(f"💻 Total systems fetched: {len(systems)}")

    recent_systems = [sys for sys in systems if was_created_within_last_24_hours(sys.get("created"))]
    print(f"⏰ Systems created in last 24h: {len(recent_systems)}")

    for system in recent_systems:
        sys_id = system.get("id")
        hostname = system.get("hostname", "").lower()
        clean_name = normalize_hostname(hostname)

        bound = get_bound_users(sys_id)
        if bound:
            print(f"⏭️ Skipping: {hostname} is already bound.")
            continue

        match = None
        for user in users:
            uname = user.get("username", "").lower().replace(".", "").replace("_", "")
            if uname in clean_name:
                match = user
                break

        if not match:
            print(f"❌ No user match found for {hostname}")
            continue

        print(f"✅ MATCH FOUND: {hostname} → {match['username']}")

        if bound:
            for u in bound:
                unbind_user(sys_id, u.get("id"))

        bind_user(sys_id, match["id"])

    end_time = time.time()
    print(f"🏁 Done in {round(end_time - start_time, 2)} seconds")


if __name__ == "__main__":
    main()
