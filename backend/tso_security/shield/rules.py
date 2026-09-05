"""Persistent state for learned rules, IP/account bans, and the attack
event feed used by the Shield dashboard.

Adapted from Sentinel Shield's rules.py. One deliberate change from
upstream: the hot-code-injection path (`load_patch_source` /
`check_patches`, which ran `exec(compile(source, ...))` on a string built
from live request content) has been REMOVED.

Why: `_generate_patch_source` in the upstream responder built Python
source text out of attacker-controlled request data (the matched pattern
and a slice of the request body) and executed it in-process. Even with
`%r`-escaping, building executable source out of untrusted input is a
code-execution risk in the exact component meant to stop attacks. The
practical benefit (auto-blocking repeats of a known bad request) is fully
covered by `add_rule` / `match_rules` below, which store the offending
pattern as DATA and match it with a plain substring/regex check — same
effect, no exec.
"""
import json
import os
import threading
import time
from collections import defaultdict, deque


class BaseRuleStore:
    """Shared logic; subclasses decide WHERE state persists."""

    def __init__(self):
        self.rules = []
        self.bans = {}
        self.strikes = defaultdict(int)
        self.events = deque(maxlen=200)
        self._lock = threading.RLock()
        self._restore()

    def _persist(self):
        raise NotImplementedError

    def _restore(self):
        pass

    def _on_event(self, event):
        pass

    # learned rules (data-only; matched by simple substring check)
    def add_rule(self, rule):
        with self._lock:
            if rule in self.rules:
                return
            self.rules.append(rule)
            self._persist()

    _TEXT_CONTENT_TYPES = ("application/json", "application/x-www-form-urlencoded",
                           "text/", "application/xml", "application/graphql")
    _MAX_BODY_SCAN_BYTES = 65536

    @classmethod
    def _extract(cls, request, field):
        if field == "url":
            return request.full_path
        if field == "user_agent":
            return request.headers.get("User-Agent", "")
        if field == "body":
            ctype = (request.content_type or "").lower()
            if not any(ctype.startswith(p) for p in cls._TEXT_CONTENT_TYPES):
                return ""
            raw = request.get_data(cache=True) or b""
            if len(raw) > cls._MAX_BODY_SCAN_BYTES:
                raw = raw[: cls._MAX_BODY_SCAN_BYTES]
            return raw.decode("utf-8", errors="replace")
        return ""

    def match_rules(self, request):
        for rule in self.rules:
            value = self._extract(request, rule.get("field", ""))
            if value and rule["pattern"].lower() in value.lower():
                return rule
        return None

    # event feed
    def record_event(self, event):
        event.setdefault("ts", round(time.time(), 3))
        with self._lock:
            self.events.appendleft(event)
        self._on_event(event)

    def recent_events(self, since=0):
        return [e for e in self.events if e.get("ts", 0) > since]

    # strikes & bans (keys are opaque: IPs or "user:<id>")
    def record_strike(self, ip):
        with self._lock:
            self.strikes[ip] += 1
            n = self.strikes[ip]
            self._persist()
        return n

    def ban(self, key, duration_seconds=3600):
        with self._lock:
            self.bans[key] = time.time() + duration_seconds
            self._persist()

    def unban(self, key):
        with self._lock:
            self.bans.pop(key, None)
            self.strikes.pop(key, None)
            self._persist()

    def is_banned(self, key):
        until = self.bans.get(key)
        if until is None:
            return False
        if until > time.time():
            return True
        self.unban(key)
        return False

    def banned(self):
        now = time.time()
        return {k: v for k, v in self.bans.items() if v > now}


class FileRuleStore(BaseRuleStore):
    """Default backend: a JSON state file + an append-only attack log.
    Good enough for a single Railway instance; swap for RedisRuleStore
    (rules_redis.py, upstream) later if TSO scales to multiple replicas.
    """

    def __init__(self, data_dir="."):
        self.data_dir = data_dir
        self.state_path = os.path.join(data_dir, "shield_state", "state.json")
        self.events_log = os.path.join(data_dir, "shield_state", "attacks.log")
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        super().__init__()

    def _restore(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path) as f:
                    d = json.load(f)
                self.rules = d.get("rules", [])
                self.bans = {k: float(v) for k, v in d.get("bans", {}).items()}
                self.strikes = defaultdict(int, d.get("strikes", {}))
                print("[SHIELD] restored %d rules, %d bans" %
                      (len(self.rules), len(self.bans)))
            except Exception as exc:
                print("[SHIELD] restore failed: %s" % exc)

    def _persist(self):
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"rules": self.rules, "bans": self.bans,
                           "strikes": dict(self.strikes)}, f, indent=2)
            os.replace(tmp, self.state_path)
        except OSError as exc:
            print("[SHIELD] persist failed: %s" % exc)

    def _on_event(self, event):
        try:
            with open(self.events_log, "a") as f:
                f.write(json.dumps(event) + "\n")
        except OSError:
            pass


class MemoryFloodTracker:
    def __init__(self):
        self._hits = defaultdict(deque)

    def is_flooding(self, ip, window, max_requests):
        now = time.time()
        q = self._hits[ip]
        while q and now - q[0] > window:
            q.popleft()
        q.append(now)
        return len(q) > max_requests
