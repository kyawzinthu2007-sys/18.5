import os
import re
import time


class AttackDetector:
    """Generic signature + flood detection (stateless -> serverless safe)."""

    SIGNATURES = {
        "SQLInjection": [
            r"(?i)(union\s+(all\s+)?select)",
            r"(?i)('|%27)\s*(or|and)\s+.+=",
            r"(?i)(or|and)\s+1\s*=\s*1",
            r"(?i)(drop\s+table|delete\s+from|insert\s+into)",
            r"(?i)(select\s+.+\s+from\s+\w+)",
        ],
        "XSS": [
            r"(?i)<script\b",
            r"(?i)on(error|load|click|mouseover)\s*=",
            r"(?i)javascript:",
            r"(?i)document\.cookie",
            r"(?i)<img\s[^>]*src[^>]*>",
            r"(?i)eval\s*\(",
        ],
        "PathTraversal": [
            r"(\.\./){2,}", r"(?i)/etc/passwd",
            r"(?i)c:\\windows", r"%2e%2e%2f",
        ],
        "CommandInjection": [
            r"(?i);\s*(cat|ls|id|whoami|wget|curl|nc|rm)\b",
            r"\$\((cat|ls|id|whoami)\)", r"\|\s*(cat|ls|id|whoami)\b",
        ],
        "KnownScanner": [
            r"(?i)(sqlmap|nikto|nmap|masscan|gobuster|dirbuster|acunetix)",
        ],
    }

    def __init__(self, window=None, max_requests=None):
        self.window = int(window or os.environ.get("RATE_LIMIT_WINDOW", 10))
        self.max_requests = int(max_requests
                                or os.environ.get("RATE_LIMIT_MAX", 40))

    # Content-Types worth scanning as text. Anything else (multipart file
    # uploads, images, PDFs, octet-stream, etc.) is skipped: binary data
    # commonly contains byte sequences that coincidentally match text
    # signatures like "onload=" or "union select", which previously caused
    # legitimate uploads (e.g. a job applicant's resume) to be flagged as
    # an attack and could escalate to an IP ban. See BUGFIX note in
    # __init__.py history / merge notes.
    _TEXT_CONTENT_TYPES = ("application/json", "application/x-www-form-urlencoded",
                           "text/", "application/xml", "application/graphql")
    _MAX_BODY_SCAN_BYTES = 65536  # cap so large legit payloads aren't fully buffered

    def _scannable_body(self, request):
        ctype = (request.content_type or "").lower()
        if not any(ctype.startswith(p) for p in self._TEXT_CONTENT_TYPES):
            return ""
        raw = request.get_data(cache=True) or b""
        if len(raw) > self._MAX_BODY_SCAN_BYTES:
            raw = raw[: self._MAX_BODY_SCAN_BYTES]
        return raw.decode("utf-8", errors="replace")

    def inspect(self, request):
        fields = {
            "url": request.full_path,
            "user_agent": request.headers.get("User-Agent", ""),
            "body": self._scannable_body(request),
        }
        for attack_type, patterns in self.SIGNATURES.items():
            for field, value in fields.items():
                if not value:
                    continue
                for pattern in patterns:
                    if re.search(pattern, value):
                        return {
                            "type": attack_type, "pattern": pattern,
                            "field": field, "sample": value[:150],
                            "ip": getattr(request, "remote_addr", "unknown"),
                            "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        return None
