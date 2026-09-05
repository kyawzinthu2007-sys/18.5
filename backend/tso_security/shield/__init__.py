"""Sentinel Shield, adapted for TSO.

Mounts as an ADDITIONAL layer alongside TSO's existing `_security_guard`
and `_security_headers` hooks in app.py -- it does not replace them.
Pipeline per request:
  L1  IP or account banned?              -> abort(403)
  L2  learned rule (data-only) matches?  -> abort(403), strike
  L2.5 endpoint-aware app firewall       -> abort(403), strike, maybe ban
  L3  generic attack signatures + flood  -> abort(403), strike, maybe ban

Differences from the upstream Sentinel Shield package:
  - No hot-code-injection ("live patch") step. See rules.py docstring.
  - No bundled AccountGuard/auth system -- TSO already has its own
    Bearer-token auth in app.py; Shield only reads request.remote_addr
    and does not touch sessions or tokens.
  - Dashboard/status endpoints are namespaced under /api/shield/* to sit
    next to TSO's existing /api/* routes.
"""
import os
import time

from flask import abort, g, jsonify, make_response, request

from . import cloudflare as cf
from .appfirewall import AppFirewall
from .detector import AttackDetector
from .responder import AutoResponder
from .rules import FileRuleStore, MemoryFloodTracker


class Shield:
    def __init__(self, app, admin_token=None, data_dir=None):
        self.admin_token = admin_token or os.environ.get(
            "SHIELD_ADMIN_TOKEN", "change-me-secret")
        self.detector = AttackDetector()
        self.appfw = AppFirewall()
        self.store = FileRuleStore(
            data_dir=data_dir or os.environ.get("SHIELD_DATA_DIR", "."))
        self.flood = MemoryFloodTracker()
        self.responder = AutoResponder(self.store)
        self.stats = {"attacks_detected": 0, "requests_blocked": 0,
                      "ips_banned": 0}

        app.before_request(self._guard)
        app.after_request(self._harden_headers)
        app.route("/api/shield/status")(self._status)
        app.route("/api/shield/unban/<target>")(self._unban)
        app.route("/api/shield/dashboard")(self._dashboard)
        app.route("/api/shield/events")(self._events)

    # ---------------- helpers ----------------
    def _auth_ok(self):
        return (request.headers.get("X-Shield-Admin-Token") == self.admin_token
                or request.cookies.get("shield_admin") == self.admin_token)

    def _client_ip(self):
        return (request.remote_addr or "unknown").strip()[:80]

    # ---------------- pipeline ----------------
    def _guard(self):
        if request.method == "OPTIONS":
            return None
        # Admin routes authenticate themselves (X-Shield-Admin-Token /
        # cookie / ?token=) and must stay reachable even when the caller's
        # own IP is banned -- otherwise a banned admin could never unban
        # themselves. Bypass the block pipeline for these paths only; the
        # route handlers below still enforce _auth_ok() on every request.
        if request.path.startswith("/api/shield/"):
            return None
        g.shield_start = time.time()
        ip = self._client_ip()

        # L1 - IP ban (account-level suspension stays with TSO's own auth)
        if self.store.is_banned(ip):
            self.stats["requests_blocked"] += 1
            abort(403)

        # L2 - learned rules (plain data match, no code execution)
        rule_hit = self.store.match_rules(request)
        if rule_hit:
            self.stats["requests_blocked"] += 1
            self.store.record_event({
                "type": rule_hit["type"], "ip": ip,
                "field": rule_hit.get("field", "url"),
                "sample": rule_hit.get("pattern", ""),
                "action": "blocked", "source": "learned-rule",
            })
            self._escalate(ip)
            abort(403)

        # L2.5 - endpoint-aware app firewall (Turbo prompt-injection etc.)
        afw = self.appfw.inspect(request)
        if afw:
            self.stats["attacks_detected"] += 1
            self.stats["requests_blocked"] += 1
            self.responder.handle(afw)
            abort(403)

        # L3 - generic zero-day signatures + rate-flood
        flooding = self.flood.is_flooding(ip, self.detector.window,
                                          self.detector.max_requests)
        attack = self.detector.inspect(request)
        if flooding or attack:
            self.stats["attacks_detected"] += 1
            info = attack or {
                "type": "RateFlooding", "pattern": "(request flood)",
                "field": "url",
                "sample": ">%d req/%ds" % (self.detector.max_requests,
                                           self.detector.window),
                "ip": ip, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
            self.responder.handle(info, flood=flooding)
            self.stats["requests_blocked"] += 1
            abort(403)
        return None

    def _escalate(self, ip):
        strikes = self.store.record_strike(ip)
        if strikes >= self.responder.ban_threshold and not self.store.is_banned(ip):
            seconds = int(os.environ.get("BAN_SECONDS", 3600))
            self.store.ban(ip, seconds)
            self.stats["ips_banned"] += 1
            if cf.configured():
                cf.block_ip(ip)
            self.store.record_event({
                "type": "AutoBan", "ip": ip, "field": "-",
                "sample": "%d strikes" % strikes,
                "action": "banned", "source": "escalation",
            })
            print("[SHIELD] *** IP %s AUTO-BANNED (strikes=%d) ***" % (ip, strikes))

    # ------------- response hardening -------------
    # NOTE: TSO's own _security_headers (app.py) already sets these same
    # headers. Flask allows multiple after_request hooks; both will run,
    # but to avoid double-setting, Shield only adds X-Shield here and
    # leaves CSP/X-Frame-Options/etc. to TSO's existing hook.
    @staticmethod
    def _harden_headers(response):
        response.headers["X-Shield"] = "active"
        return response

    # ------------- admin endpoints -------------
    def _status_payload(self):
        return {
            "stats": self.stats,
            "backend": type(self.store).__name__,
            "cloudflare_sync": cf.configured(),
            "banned_ips": {k: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v))
                           for k, v in sorted(self.store.banned().items())},
            "learned_rules": len(self.store.rules),
        }

    def _status(self):
        if not self._auth_ok():
            abort(403)
        return jsonify(self._status_payload())

    def _unban(self, target):
        if not self._auth_ok():
            abort(403)
        self.store.unban(target)
        if cf.configured():
            cf.unblock_ip(target)
        return jsonify({"ok": True, "unbanned": target})

    def _events(self):
        if not self._auth_ok():
            abort(403)
        try:
            since = float(request.args.get("since", 0))
        except ValueError:
            since = 0
        return jsonify({"now": time.time(), "events": self.store.recent_events(since)})

    def _dashboard(self):
        from .dashboard import DASHBOARD_HTML
        token = request.args.get("token") or request.cookies.get("shield_admin")
        if token != self.admin_token:
            abort(403)
        html = DASHBOARD_HTML.replace(
            "__BOOTSTRAP__", __import__("json").dumps(self._status_payload()))
        resp = make_response(html)
        if not request.cookies.get("shield_admin"):
            resp.set_cookie("shield_admin", self.admin_token,
                            max_age=7 * 24 * 3600, httponly=True, samesite="Lax")
        return resp
