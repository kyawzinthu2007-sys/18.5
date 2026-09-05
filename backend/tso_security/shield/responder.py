"""Reacts to a detected attack: learns a rule (as data, not code), strikes
the source, escalates to a ban past a threshold, and fires an email alert.

Adapted from Sentinel Shield's responder.py. Upstream also generated a
Python source string per-attack and exec'd it ("hot-injected patch") --
that step is removed here. See rules.py module docstring for why.
"""
import os

from . import alerts


class AutoResponder:
    def __init__(self, store, ban_threshold=None):
        self.store = store
        self.ban_threshold = int(ban_threshold
                                  or os.environ.get("SHIELD_BAN_THRESHOLD", 3))

    def handle(self, attack, flood=False):
        ip = attack.get("ip", "unknown")

        # Learn a plain data rule so repeats of this exact pattern/field
        # are matched (and blocked) on the next request without needing
        # to re-run full signature detection.
        if not flood and attack.get("pattern") and attack.get("field"):
            self.store.add_rule({
                "type": attack["type"],
                "pattern": attack["pattern"],
                "field": attack["field"],
            })

        self.store.record_event({
            "type": attack["type"],
            "ip": ip,
            "field": attack.get("field", "-"),
            "sample": attack.get("sample", ""),
            "endpoint": attack.get("endpoint", "-"),
            "action": "blocked",
            "source": "app-firewall" if attack.get("endpoint") else "detector",
        })

        strikes = self.store.record_strike(ip)
        banned_now = False
        if strikes >= self.ban_threshold and not self.store.is_banned(ip):
            seconds = int(os.environ.get("BAN_SECONDS", 3600))
            self.store.ban(ip, seconds)
            banned_now = True
            self.store.record_event({
                "type": "AutoBan", "ip": ip, "field": "-",
                "sample": "%d strikes" % strikes,
                "action": "banned", "source": "escalation",
            })
            print("[SHIELD] *** IP %s AUTO-BANNED (strikes=%d) ***"
                  % (ip, strikes))

        if banned_now or strikes >= self.ban_threshold:
            try:
                alerts.send_attack_alert(attack)
            except Exception as exc:
                print("[SHIELD] alert dispatch failed: %s" % exc)
