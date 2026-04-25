# freecustom.email mail service — https://www.freecustom.email/api/docs/quickstart
import time
import requests
import re
import random
import string
import os
import json
from urllib.parse import quote

class TempTfMailApi:
    BASE_URL = "https://api2.freecustom.email/v1"
    INBOXES_ENDPOINT = f"{BASE_URL}/inboxes"
    DEFAULT_DOMAIN = "junkstopper.info"

    def __init__(self, logger=None, forced_domain: str = None, api_key: str = None):
        self.created_emails = {}
        self.logger = logger
        self.forced_domain = forced_domain
        self.api_key = (api_key or os.getenv("FCE_API_KEY", "")).strip()
        if not self.api_key:
            self.api_key = self._read_api_key_from_config()

    def _build_proxies(self, proxy: str = None):
        if proxy and "://" not in proxy:
            proxy = f"http://{proxy}"
        return {"http": proxy, "https": proxy} if proxy else None

    def _log(self, message: str):
        pass

    def _headers(self):
        if not self.api_key:
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _read_api_key_from_config(self):
        try:
            with open("input/config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
            mail_cfg = cfg.get("mail", {}) if isinstance(cfg, dict) else {}
            key = mail_cfg.get("api_key") or mail_cfg.get("fce_api_key")
            return (key or "").strip()
        except Exception:
            return ""

    def create_account(self, email: str = None, password: str = None, proxy: str = None):
        if email and '@' in email:
            created_email = email
        elif self.forced_domain:
            local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            created_email = f"{local}@{self.forced_domain}"
        else:
            created_email = self._create_temp_account(proxy=proxy)

        if not created_email:
            self._log("freecustom.email could not create an email")
            return None

        if not self._register_inbox(created_email, proxy=proxy):
            self._log(f"Failed to register inbox: {created_email}")
            return None

        self.created_emails[created_email] = password or ""
        self._log(f"Prepared email: {created_email}")
        return created_email

    def _create_temp_account(self, proxy: str = None):
        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        return f"{local}@{self.DEFAULT_DOMAIN}"

    def _register_inbox(self, email: str, proxy: str = None) -> bool:
        if not self.api_key:
            self._log("FCE_API_KEY is missing; cannot register inbox")
            return False
        proxies = self._build_proxies(proxy)
        payload = {"inbox": email}
        try:
            resp = requests.post(
                self.INBOXES_ENDPOINT,
                json=payload,
                headers=self._headers(),
                timeout=20,
                proxies=proxies,
            )
            if resp.status_code in (200, 201):
                self._log(f"Registered freecustom.email inbox: {email}")
                return True

            self._log(f"freecustom.email register failed for {email}")
            return False
        except Exception as e:
            self._log(f"freecustom.email register exception: {e}")
            return False

    def get_verify_url(self, email: str, poll_interval: int = 3, timeout: int = 120, proxy: str = None):
        start_time = time.time()
        used_message_ids = set()
        
        while time.time() - start_time < timeout:
            try:
                messages = self._read_inbox(email, proxy=proxy)
                if messages:
                    for msg in messages:
                        msg_id = msg.get("id")
                        if msg_id in used_message_ids:
                            continue
                        
                        subject = msg.get("subject", "")
                        direct_link = msg.get("verification_link") or msg.get("verificationLink")
                        if direct_link and ("discord.com" in direct_link or "click.discord.com" in direct_link):
                            return direct_link

                        if "discord" in subject.lower() or "verify" in subject.lower() or "verif" in subject.lower():
                            detail = self._read_message_detail(email, msg_id, proxy=proxy) if msg_id else None
                            html_body = (detail.get("html", "") if detail else "") or msg.get("html", "")
                            text_body = (detail.get("body", "") if detail else "") or msg.get("body", "")
                            detail_link = (detail.get("verification_link") if detail else "") or ""
                            if detail_link and ("discord.com" in detail_link or "click.discord.com" in detail_link):
                                return detail_link
                            combined = html_body + text_body
                            
                            all_links = re.findall(r'https?://[^\s"\'<>]+', combined)
                            target_links = [l for l in all_links if ("discord.com" in l or "click.discord.com" in l) and "support." not in l and "blog." not in l]
                            
                            if target_links:
                                url = None
                                if len(target_links) >= 2:
                                    second_url = target_links[1]
                                    if "verify" in second_url.lower() or "token=" in second_url.lower() or "click.discord.com" in second_url:
                                        url = second_url
                                        self._log(f"Using second URL (Discord pattern)")
                                
                                if not url:
                                    url = max(target_links, key=len)
                                    self._log(f"Using longest URL")
                                
                                if "click.discord.com" in url:
                                    self._log(f"Resolving: {url[:30]}...")
                                    resolved = self._resolve_url(url, proxy=proxy)
                                    if resolved:
                                        return resolved
                                return url
                            used_message_ids.add(msg_id)
            except Exception as e:
                self._log(f"Error reading inbox: {e}")
            time.sleep(poll_interval)
            
        self._log(f"Timeout waiting for verify URL in {email}")
        return None

    def _read_message_detail(self, email: str, message_id: str, proxy: str = None):
        if not self.api_key or not email or not message_id:
            return None
        proxies = self._build_proxies(proxy)
        encoded_email = quote(email, safe="")
        encoded_id = quote(str(message_id), safe="")
        url = f"{self.INBOXES_ENDPOINT}/{encoded_email}/messages/{encoded_id}"
        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                timeout=15,
                proxies=proxies,
            )
            if not resp.ok:
                return None
            data = resp.json()
            msg = data.get("data", {}) if isinstance(data, dict) else {}
            if not isinstance(msg, dict):
                return None
            return {
                "id": msg.get("id") or msg.get("message_id") or msg.get("_id"),
                "subject": msg.get("subject", ""),
                "body": msg.get("text", "") or msg.get("body", "") or msg.get("plain", ""),
                "html": msg.get("html", "") or msg.get("html_body", "") or msg.get("bodyHtml", ""),
                "verification_link": msg.get("verification_link") or msg.get("verificationLink") or "",
            }
        except Exception:
            return None

    def _resolve_url(self, url: str, proxy: str = None) -> str:
        if proxy and "://" not in proxy:
            proxy = f"http://{proxy}"
        proxies = {"http": proxy, "https": proxy} if proxy else None
        try:
            resp = requests.head(url, allow_redirects=True, timeout=10, proxies=proxies)
            final_url = resp.url
            if "discord.com/verify" in final_url:
                self._log(f"Resolved tracker to: {final_url[:40]}...")
                return final_url
        except Exception:
            pass
        return None

    def delete_inbox(self, email: str):
        # Not required for flow; we only skip old message ids while polling.
        return True

    def _read_inbox(self, email: str, proxy: str = None):
        if not self.api_key:
            return None
        proxies = self._build_proxies(proxy)
        encoded_email = quote(email, safe="")
        url = f"{self.INBOXES_ENDPOINT}/{encoded_email}/messages"
        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                timeout=15,
                proxies=proxies,
            )

            if not resp.ok:
                return None

            data = resp.json()
            messages = data.get("data", []) if isinstance(data, dict) else []
            if isinstance(messages, dict):
                messages = messages.get("messages", []) or messages.get("items", [])
            if not isinstance(messages, list):
                messages = []

            normalized = []
            for msg in messages:
                html = msg.get("html", "") or msg.get("html_body", "") or msg.get("bodyHtml", "")
                text = msg.get("text", "") or msg.get("body", "") or msg.get("plain", "")
                normalized.append({
                    "id": msg.get("id") or msg.get("message_id") or msg.get("_id"),
                    "from": msg.get("from"),
                    "to": msg.get("to"),
                    "subject": msg.get("subject", ""),
                    "body": text,
                    "html": html,
                    "verification_link": msg.get("verification_link") or msg.get("verificationLink") or "",
                })
            return normalized
        except Exception:
            return None
