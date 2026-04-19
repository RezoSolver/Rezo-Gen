import stealth_requests as requests
from stealth_requests import StealthSession
import time
import random
from urllib.parse import urlparse

class Solver:
    def __init__(self, url, sitekey, rqdata="", user_agent="", proxy=None, api_key=None):
        self.url        = url
        self.sitekey    = sitekey
        self.rqdata     = rqdata
        self.user_agent = user_agent
        self.proxy      = proxy
        self.api_key    = api_key
        self.server_url = "https://huzaif.online"

    def _parse_proxy(self):
        if not self.proxy:
            return {}
        raw = self.proxy
        if "://" not in raw:
            raw = "http://" + raw
        try:
            parsed = urlparse(raw)
        except Exception as e:
            return {}
            
        result = {}
        if parsed.hostname and parsed.port:
            result["srv"] = f"{parsed.hostname}:{parsed.port}"
        if parsed.username:
            result["usr"] = parsed.username
        if parsed.password:
            result["pw"] = parsed.password
        return result

    def solve(self, timeout=300, poll_interval=1):
        payload = {
            "api_key":    self.api_key,
            "url":        self.url,
            "sitekey":    self.sitekey,
            "rqdata":     self.rqdata,
            "user_agent": self.user_agent,
        }
        proxy_data = self._parse_proxy()
        payload.update(proxy_data)

        sess = StealthSession()
        if self.user_agent:
            sess.headers.update({"User-Agent": self.user_agent})

        try:
            resp = sess.post(f"{self.server_url}/solve", json=payload, timeout=30)
        except Exception:
            return None, None

        if resp.status_code != 200:
            return None, None

        try:
            data = resp.json()
        except Exception:
            return None, None

        taskid = data.get("taskid")
        if not taskid:
            return None, None

        start = time.time()
        while time.time() - start < timeout:
            try:
                poll_resp = sess.post(
                    f"{self.server_url}/task/{taskid}",
                    json={"api_key": self.api_key},
                    timeout=30,
                )
            except Exception:
                time.sleep(poll_interval + random.uniform(0, 0.5))
                continue

            if poll_resp.status_code != 200:
                time.sleep(poll_interval + random.uniform(0, 0.5))
                continue

            try:
                d = poll_resp.json()
            except Exception:
                time.sleep(poll_interval + random.uniform(0, 0.5))
                continue

            status  = d.get("status")
            uuid    = d.get("uuid")
            cookies = d.get("cookies", {})

            if status == "success":
                return uuid, cookies
            if status in {"failed", "error", "not_found"}:
                return None, None

            time.sleep(poll_interval + random.uniform(0, 0.5))
        return None, None
