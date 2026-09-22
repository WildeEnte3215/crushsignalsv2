"""Small REST client: no SDK initialization or urllib3/LibreSSL dependency."""

import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import certifi
from .utils import ProductionError, atomic


class APIError(ProductionError):
    def __init__(self, status, message):
        self.status = status
        super().__init__("HTTP %s: %s" % (status, message))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlparse(req.full_url), urllib.parse.urlparse(newurl)
        sensitive = any(
            k.lower() in ("authorization", "xi-api-key") for k in req.headers
        )
        if new.scheme != "https" or (sensitive and old.netloc != new.netloc):
            raise APIError(code, "Blocked unsafe credential redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Http:
    def __init__(self, secrets=()):
        self.secrets = [s for s in secrets if s]
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=certifi.where())
            ),
            SafeRedirect(),
        )

    def redact(self, message):
        message = str(message)
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        return re.sub(r"([?&]key=)[^&\s]+", r"\1[REDACTED]", message)

    def request(self, method, url, headers=None, body=None, binary=False, before=None):
        if not url.startswith("https://"):
            raise ProductionError("HTTPS required")
        data = None if body is None else json.dumps(body).encode()
        hdr = {"User-Agent": "WorldIn60/1.0", **(headers or {})}
        if data is not None:
            hdr["Content-Type"] = "application/json"
        for attempt in range(3):
            if before:
                before()  # Reserve every attempted billable request, including retries.
            try:
                req = urllib.request.Request(url, data=data, headers=hdr, method=method)
                with self.opener.open(req, timeout=120) as response:
                    raw = response.read(180000001)
                if len(raw) > 180000000:
                    raise ProductionError("Response exceeds 180 MB limit")
                if binary:
                    return raw
                try:
                    return json.loads(raw)
                except ValueError as e:
                    raise ProductionError(
                        "API returned malformed JSON; no blind paid retry."
                    ) from e
            except urllib.error.HTTPError as e:
                reason = self.redact(e.read(4096).decode("utf-8", "replace"))
                if (
                    e.code not in (408, 429, 500, 502, 503, 504)
                    or "insufficient_quota" in reason
                ):
                    raise APIError(e.code, reason) from None
                delay = e.headers.get("Retry-After", "")
                delay = (
                    float(delay)
                    if delay.replace(".", "", 1).isdigit()
                    else 2 ** (attempt + 1)
                )
                if attempt == 2 or delay > 30:
                    raise APIError(
                        e.code, reason + " Resume later; intermediate work is saved."
                    ) from None
                time.sleep(delay + random.random())
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt == 2:
                    raise APIError("network", self.redact(e)) from None
                time.sleep(2 ** (attempt + 1))

    def download(self, url, path):
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        allowed = (
            "pexels.com",
            "pixabay.com",
            "vimeo.com",
            "vimeocdn.com",
            "akamaized.net",
        )
        if not any(host == h or host.endswith("." + h) for h in allowed):
            raise ProductionError("Stock download host is not allowed: " + host)
        atomic(path, self.request("GET", url, binary=True))
