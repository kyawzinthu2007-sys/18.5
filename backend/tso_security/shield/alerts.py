import os

try:
    import requests
except ImportError:
    requests = None

ENDPOINT = "https://api.resend.com/emails"


def configured():
    return bool(os.environ.get("RESEND_API_KEY")) and requests is not None


def send_attack_alert(attack, extra_html=""):
    if not configured():
        return False
    from_addr = os.environ.get("ALERT_EMAIL_FROM")
    to_addrs = [a.strip() for a in
                os.environ.get("ALERT_EMAIL_TO", "").split(",") if a.strip()]
    if not from_addr or not to_addrs:
        return False
    sample = (attack.get("sample") or "").replace("<", "&lt;")[:300]
    html = ("<div style='font-family:sans-serif'>"
            "<h2>Sentinel Shield - attack blocked</h2>"
            "<p><b>Type:</b> %s</p><p><b>Source:</b> %s</p>"
            "<p><b>Endpoint:</b> %s</p><p><b>Payload:</b></p><pre>%s</pre>%s"
            "</div>") % (attack.get("type"), attack.get("ip"),
                         attack.get("endpoint", "-"), sample, extra_html)
    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": "Bearer "
                     + os.environ["RESEND_API_KEY"]},
            json={"from": from_addr, "to": to_addrs,
                  "subject": "[SHIELD] %s from %s"
                             % (attack.get("type"), attack.get("ip")),
                  "html": html},
            timeout=5)
        return resp.status_code in (200, 202)
    except Exception as exc:
        print("[SHIELD] alert error: %s" % exc)
        return False
