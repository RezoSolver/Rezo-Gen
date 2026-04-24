# cybertemp is flagged rn, if its not working then host your own mail
import time
import requests
import random
import re
from urllib.parse import unquote

class CybertempMailApi:
    BASE_URL = "https://api.cybertemp.xyz"
    DOMAINS = [
        "picturehostel.store",
    ]
    
    def __init__(self, api_key: str = None, logger=None):
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key} if api_key else {}
        self.created_emails = {}
        self.logger = logger

    def _log(self, message: str):
        if not self.logger:
            return
        if hasattr(self.logger, "debug"):
            try:
                self.logger.debug(message)
                return
            except Exception:
                pass
        try:
            self.logger(message)
        except Exception:
            pass

    def create_account(self, email: str = None, password: str = None):
        if email and '@' in email:
            created_email = email
        else:
            username = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=12))
            domain = random.choice(self.DOMAINS)
            created_email = f"{username}@{domain}"
            
        self.created_emails[created_email] = password or ""
        self._log(f"Prepared Cybertemp email: {created_email}")
        return created_email

    def get_verify_url(self, email: str, poll_interval: int = 3, timeout: int = 120, proxy: str = None):
        self.delete_inbox(email)
        start_time = time.time()
        used_message_ids = set()
        
        while time.time() - start_time < timeout:
            try:
                messages = self._read_inbox(email)
                if messages:
                    for msg in messages:
                        msg_id = msg.get("id")
                        if msg_id in used_message_ids:
                            continue
                        
                        subject = msg.get("subject", "")
                        if "discord" in subject.lower() or "verify" in subject.lower() or "verif" in subject.lower():
                            html_body = msg.get("html", "") 
                            text_body = msg.get("body", "")
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
        try:
            resp = requests.delete(
                f"{self.BASE_URL}/user/inboxes",
                headers=self.headers,
                json={"inbox_address": email},
                timeout=15
            )
            if resp.ok:
                self._log(f"Deleted inbox: {email}")
                return True
        except Exception:
            pass
        return False

    def _read_inbox(self, email: str, proxy: str = None):
        if proxy and "://" not in proxy:
            proxy = f"http://{proxy}"
        proxies = {"http": proxy, "https": proxy} if proxy else None
        try:
            resp = requests.get(
                f"{self.BASE_URL}/getMail",
                params={"email": email},
                headers=self.headers,
                timeout=15,
                proxies=proxies
            )
            
            if not resp.ok:
                return None
            
            data = resp.json()
            messages = data.get("emails", []) if isinstance(data, dict) else data
            
            normalized = []
            for msg in messages:
                normalized.append({
                    "id": msg.get("id"),
                    "from": msg.get("from"),
                    "to": msg.get("to"),
                    "subject": msg.get("subject", ""),
                    "body": msg.get("body") or msg.get("text") or "",
                    "html": msg.get("html", "")
                })
            return normalized
        except Exception:
            return None
