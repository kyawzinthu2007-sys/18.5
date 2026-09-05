import os

try:
    import requests
except ImportError:
    requests = None

API = "https://api.cloudflare.com/client/v4"


def configured():
    return (requests is not None
            and bool(os.environ.get("CF_API_TOKEN"))
            and bool(os.environ.get("CF_ZONE_ID")))


def _headers():
    return {"Authorization": "Bearer " + os.environ["CF_API_TOKEN"],
            "Content-Type": "application/json"}


def block_ip(ip):
    if not configured():
        return None
    zone = os.environ["CF_ZONE_ID"]
    try:
        resp = requests.post(
            "%s/zones/%s/firewall/access_rules/rules" % (API, zone),
            headers=_headers(),
            json={"mode": "block",
                  "configuration": {"target": "ip", "value": ip},
                  "notes": "Sentinel Shield auto-ban"},
            timeout=6)
        data = resp.json()
        if resp.status_code in (200, 201) and data.get("success"):
            return data["result"]["id"]
        errors = str(data.get("errors", ""))
        if "already_exists" in errors or "81057" in errors:
            return "existing"
        print("[SHIELD] CF block failed: %s %s"
              % (resp.status_code, errors[:120]))
    except Exception as exc:
        print("[SHIELD] CF error: %s" % exc)
    return None


def unblock_ip(ip):
    if not configured():
        return 0
    zone = os.environ["CF_ZONE_ID"]
    removed = 0
    try:
        resp = requests.get(
            "%s/zones/%s/firewall/access_rules/rules"
            "?mode=block&configuration.target=ip&configuration.value=%s"
            "&per_page=50" % (API, zone, ip),
            headers=_headers(), timeout=6)
        data = resp.json()
        if not data.get("success"):
            return 0
        for item in data.get("result", []):
            cid = item.get("id")
            if cid:
                dele = requests.delete(
                    "%s/zones/%s/firewall/access_rules/rules/%s"
                    % (API, zone, cid), headers=_headers(), timeout=6)
                if dele.status_code == 200:
                    removed += 1
    except Exception as exc:
        print("[SHIELD] CF unblock error: %s" % exc)
    return removed
