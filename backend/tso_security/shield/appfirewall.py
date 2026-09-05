"""Endpoint-scoped scanning for TSO's actual product surfaces:
/api/ai/chat            -> LLM prompt-injection + role-tag smuggling (Turbo)
/api/jobs                -> job-post spam, scam links, redirector shorteners
/edu/api/generate-essay  -> essay-coach prompt-injection + grade tampering
/api/credit              -> client-side price/credit tampering

Adapted from Sentinel Shield's appfirewall.py. Differences from upstream:
  - Path prefixes rewritten to match TSO's real routes (upstream assumed
    /api/essays and /api/subscription, which TSO does not have).
  - No hot-code-injection path: matches are pure regex, no exec/compile of
    request-derived text. See rules.py for why that piece was dropped.
"""
import re
import time

RULESETS = {  # path-prefix -> [(attack_type, [regexes]), ...]
    "/api/ai/chat": [
        ("PromptInjection", [
            r"(?i)ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions",
            r"(?i)disregard\s+(your|the)\s+(rules|instructions|guidelines)",
            r"(?i)you\s+are\s+now\s+(a|an|no longer)",
            r"(?i)reveal\s+(your\s+)?(initial|original|system)\s+(prompt|instructions)",
            r"(?i)(developer|god|jailbreak)\s*mode",
            r"(?i)print\s+everything\s+(before|above)",
            r"(?:^|\n)\s*(system|assistant)\s*:",
        ]),
        ("ContextOverwrite", [
            r"</?\s*(system|assistant)\s*>",
            r"(?i)new\s+system\s+prompt\s*:",
        ]),
    ],
    "/api/jobs": [
        ("SpamContent", [
            r"(?i)(viagra|casino|porn|escort)\b",
            r"(?i)crypto\s+(giveaway|doubling)|double\s+your\s+(btc|eth|money)",
            r"(?i)forex\s+signals?|guaranteed\s+profit",
            r"(?i)https?://(bit\.ly|tinyurl\.com|t\.me|cutt\.ly|shorturl\.at)/",
            r"(?i)(earn|make)\s*\$\s?\d[\d,.]*\s*(a|per)?\s*(day|week|hour)?"
            r".*(home|online)",
            r"(?i)whats?app(\s|\+)?(\d|[a-z])",
        ]),
        ("HiddenText", [
            r"display\s*:\s*none", r"font-size\s*:\s*0",
            r"<!--[\s\S]*-->",
        ]),
    ],
    "/edu/api/generate-essay": [
        ("PromptInjection", [
            r"(?i)ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions",
            r"(?i)grade\s+(this\s+)?as\s+(a|an)\s+A\+\+?",
            r"(?i)output\s+score\s*[:=]?\s*100",
            r"(?i)you\s+are\s+now\s+(a|an)",
        ]),
    ],
    "/api/credit": [
        ("CreditTamper", [
            r"\"(credits|coins)\"\s*:\s*-",
            r"\"(cost|price|amount)\"\s*:\s*(-|1e\d|9{6,})",
            r"(?i)LIFETIME|FREE_?UPGRADE|UNLIMITED",
        ]),
    ],
}


class AppFirewall:
    # Same false-positive risk as the generic detector: only scan bodies
    # whose Content-Type indicates text, and cap how much is buffered.
    _TEXT_CONTENT_TYPES = ("application/json", "application/x-www-form-urlencoded",
                           "text/", "application/xml", "application/graphql")
    _MAX_BODY_SCAN_BYTES = 65536

    def _scannable_body(self, request):
        ctype = (request.content_type or "").lower()
        if not any(ctype.startswith(p) for p in self._TEXT_CONTENT_TYPES):
            return ""
        raw = request.get_data(cache=True) or b""
        if len(raw) > self._MAX_BODY_SCAN_BYTES:
            raw = raw[: self._MAX_BODY_SCAN_BYTES]
        return raw.decode("utf-8", errors="replace")

    def inspect(self, request):
        path = request.path or ""
        rulesets = None
        for prefix in RULESETS:
            if path.startswith(prefix):
                rulesets = RULESETS[prefix]
                break
        if not rulesets:
            return None

        body = self._scannable_body(request)
        fields = {"url": request.full_path, "body": body}
        for attack_type, patterns in rulesets:
            for field, value in fields.items():
                if not value:
                    continue
                for pattern in patterns:
                    if re.search(pattern, value):
                        return {
                            "type": attack_type,
                            "pattern": pattern,
                            "field": field,
                            "sample": value[:150],
                            "endpoint": path,
                            "ip": getattr(request, "remote_addr", "unknown"),
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
        return None
