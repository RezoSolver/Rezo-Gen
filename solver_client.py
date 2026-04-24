import stealth_requests as requests
from stealth_requests import StealthSession
import time
import random
from urllib.parse import urlparse

class Solver:
    def __init__(self, url, sitekey, rqdata="", user_agent="", proxy=None, api_key=""):
        self.url        = url
        self.sitekey    = sitekey
        self.rqdata     = rqdata
        self.user_agent = user_agent
        self.proxy      = proxy
        self.api_key    = api_key
        self.server_url = "http://huzaif.online"

    def _format_proxy(self):
        if not self.proxy:
            return None
        raw = self.proxy
        if "://" not in raw:
            raw = "http://" + raw
        return raw

    def solve(self, timeout=300, poll_interval=1):
        sess = StealthSession()
        if self.user_agent:
            sess.headers.update({"User-Agent": self.user_agent})
        task = {
            "site_url": self.url,
            "site_key": self.sitekey,
        }
        if self.rqdata:
            task["rqdata"] = self.rqdata
        if self.user_agent:
            task["ua"] = self.user_agent
        proxy_str = self._format_proxy()
        if proxy_str:
            task["proxy"] = proxy_str

        create_payload = {
            "clientKey": self.api_key,
            "task": task
        }

        # Create task — POST /createtask
        try:
            resp = sess.post(f"{self.server_url}/createtask", json=create_payload, timeout=30)
        except Exception as e:
            print(f"Error initiating solve: {e}")
            return None, None

        if resp.status_code != 200:
            try:
                err = resp.json()
                print(f"Error initiating solve: {resp.status_code} - {err}")
            except Exception:
                print(f"Error initiating solve: {resp.status_code}")
            return None, None

        try:
            data = resp.json()
        except Exception:
            return None, None

        task_id = data.get("taskId")
        if not task_id:
            print(f"Error: No taskId received - {data}")
            return None, None

        # Poll for result — POST /gettaskresult
        start = time.time()
        while time.time() - start < timeout:
            try:
                poll_resp = sess.post(
                    f"{self.server_url}/gettaskresult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=30
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

            status = d.get("status")
            uuid_token = d.get("uuid")

            if status == "success" and uuid_token:
                return uuid_token, {}
            if status in {"error", "timeout"}:
                return None, None

            time.sleep(poll_interval + random.uniform(0, 0.5))

        return None, None
