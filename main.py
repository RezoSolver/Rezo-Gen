import stealth_requests as requests
from stealth_requests import StealthSession
import base64
import json
import os
import platform
import random
import re
import string
import threading
import time
import uuid
import websocket
import ctypes
from datetime import datetime
from urllib.parse import urlparse

from mail import TempTfMailApi
from solver_client import Solver

config = {}
try:
    with open("input/config.json", "r") as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config.json: {e}")

mail_api = TempTfMailApi(logger=print, api_key=config.get("mail", {}).get("api_key"))
verification_enabled = config.get("verification", {}).get("enabled", True)

gen_count = 0
gen_lock = threading.Lock()

stats_lock = threading.Lock()
stats = {
    'generated': 0,
    'verified': 0,
    'captcha_failed': 0,
    'captcha_solved': 0,
    'locked': 0,
    'valid': 0,
    'total': 0
}

class ProxyManager:
    def __init__(self, file_path="input/proxies.txt"):
        self.file_path = file_path
        self.lock = threading.Lock()
        
    def pop_top(self):
        with self.lock:
            if not os.path.exists(self.file_path):
                return None
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    lines = [line for line in f if line.strip()]
                if not lines:
                    return None
                proxy = lines.pop(0).strip()
                with open(self.file_path, "w", encoding="utf-8") as f:
                    for line in lines:
                        if not line.endswith('\n'):
                            line += '\n'
                        f.write(line)
                
                user_pass = ""
                host_port = ""
                if "@" in proxy:
                    user_pass, host_port = proxy.split("@", 1)
                else:
                    host_port = proxy

                if "dataimpulse" in host_port.lower() and user_pass:
                    if ":" in user_pass:
                        user, pwd = user_pass.split(":", 1)
                        if "__session" not in user:
                            sess_id = uuid.uuid4().hex[:8]
                            user_pass = f"{user}__session_{sess_id}:{pwd}"

                import socket
                if ":" in host_port:
                    host, port = host_port.rsplit(":", 1)
                    try:
                        resolved_ip = socket.gethostbyname(host)
                        host_port = f"{resolved_ip}:{port}"
                    except Exception:
                        pass

                if user_pass:
                    proxy = f"{user_pass}@{host_port}"
                else:
                    proxy = host_port
                return proxy
            except Exception:
                return None

proxy_manager = ProxyManager()

from colorama import Fore, Style, init
from pystyle import Colors, Colorate, Center, Anime, System

init(autoreset=True)

class Log:
    lock = threading.Lock()

    @staticmethod
    def _log(label, text, color=Fore.WHITE):
        padded = label.ljust(12)
        with Log.lock:
            print(f"{Fore.LIGHTBLACK_EX}[REZO SOLVER]{Style.RESET_ALL} {color}{padded}{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} {text}")

    @staticmethod
    def proxy_header(num, proxy):
        with Log.lock:
            if proxy:
                host_port = proxy.split("@")[-1]
                proxy_text = f"****@{host_port}"
            else:
                proxy_text = "direct"
            
            
            print(f"\n{Fore.CYAN}THREAD {num} | PROXY: {proxy_text}{Style.RESET_ALL}")

    @staticmethod
    def generated(token):
        Log._log("[+] GENERATED", f"{token[:35]}...", Fore.GREEN)
        with stats_lock:
            stats['generated'] += 1
            stats['total'] += 1

    @staticmethod
    def captcha_solved(time_n):
        Log._log("[✓] CAPTCHA", f"Solved ({time_n:.1f}s)", Fore.CYAN)
        with stats_lock:
            stats['captcha_solved'] += 1

    @staticmethod
    def solving(email):
        Log._log("[-] SOLVING", f"Solving with Rezo Solver | {email}", Fore.YELLOW)

    @staticmethod
    def captcha_failed():
        Log._log("[-] CAPTCHA", "Failed to solve", Fore.RED)
        with stats_lock:
            stats['captcha_failed'] += 1
            stats['total'] += 1

    @staticmethod
    def status(status_text):
        Log._log("[*] STATUS", status_text, Fore.MAGENTA)

    @staticmethod
    def error(text):
        Log._log("[x] ERROR", text, Fore.RED)

    @staticmethod
    def waiting(text):
        Log._log("[-] WAITING", text, Fore.YELLOW)

    @staticmethod
    def verified(token):
        Log._log("[+] VERIFIED", f"{token[:40]}...", Fore.GREEN)
        with stats_lock:
            stats['verified'] += 1

CHROME_VERSION = 124
USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"

def get_build_number(proxy=None):
    try:
        sess = StealthSession()
        if proxy:
            proxy_url = f"http://{proxy}" if "://" not in proxy else proxy
            sess.proxies = {"http": proxy_url, "https": proxy_url}
        page = sess.get("https://discord.com/app").text
        assets = re.findall(r'src="/assets/([^"]+)"', page)
        for asset in reversed(assets):
            js = sess.get(f"https://discord.com/assets/{asset}").text
            if "buildNumber:" in js:
                return int(js.split('buildNumber:"')[1].split('"')[0]) 
    except Exception:
        pass
    return 502645

def build_super_properties(build_number):
    payload = {
        "os": "Windows",
        "browser": "Chrome",
        "device": "",
        "system_locale": "en-US",
        "browser_user_agent": USER_AGENT,
        "browser_version": f"{CHROME_VERSION}.0.0.0",
        "os_version": platform.release(),
        "referrer": "https://discord.com/",
        "referring_domain": "discord.com",
        "referrer_current": "",
        "referring_domain_current": "",
        "release_channel": "stable",
        "client_build_number": build_number,
        "client_event_source": None,
        "has_client_mods": False,
        "client_launch_id": str(uuid.uuid4()),
        "launch_signature": str(uuid.uuid4()),
        "client_heartbeat_session_id": str(uuid.uuid4()),
        "client_app_state": "focused",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode()

def fetch_cookies(session):
    session.get("https://discord.com")
    cookies = session.cookies.get_dict()
    dcfduid = cookies.get("__dcfduid")
    sdcfduid = cookies.get("__sdcfduid")
    return dcfduid, sdcfduid

def get_fingerprint(session, dcfduid, sdcfduid):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "cookie": f"__dcfduid={dcfduid}; __sdcfduid={sdcfduid};",
        "sec-ch-ua": f'"Chromium";v="{CHROME_VERSION}", "Google Chrome";v="{CHROME_VERSION}", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": USER_AGENT
    }
    session.headers = headers
    data = session.get("https://discord.com/api/v9/experiments")
    return data.json()["fingerprint"]

def build_headers(fingerprint, super_props):
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://discord.com",
        "referer": "https://discord.com/",
        "priority": "u=1, i",
        "sec-ch-ua": f'"Chromium";v="{CHROME_VERSION}", "Google Chrome";v="{CHROME_VERSION}", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": USER_AGENT,
        "x-debug-options": "bugReporterEnabled",
        "x-discord-locale": "en-US",
        "x-discord-timezone": "America/Los_Angeles",
        "x-fingerprint": fingerprint,
        "x-super-properties": super_props,
    }

def check_token_status(session):
    try:
        r = session.get("https://discord.com/api/v9/users/@me")
        if r.status_code != 200:
            return "invalid"
        r2 = session.get("https://discord.com/api/v9/users/@me/settings")
        if r2.status_code == 200:
            return "Valid"
        elif r2.status_code == 403:
            return "locked"
    except Exception:
        pass
    return "invalid"

def save_account(email, password, token, token_status):
    os.makedirs("output", exist_ok=True)
    if token_status == "Valid":
        filename = "output/valid.txt"
        with stats_lock:
            stats['valid'] += 1
    elif token_status == "locked":
        filename = "output/locked.txt"
        with stats_lock:
            stats['locked'] += 1
    else:
        filename = "output/invalid.txt"
    
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{email}:{password}:{token}\n")

class BackgroundOnliner:
    """Keeps a token online via Discord gateway in a background thread."""
    def __init__(self, token):
        self.token = token
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            ws = websocket.WebSocket()
            ws.settimeout(10)
            ws.connect("wss://gateway.discord.gg/?v=9&encoding=json")
            hello = json.loads(ws.recv())
            heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000

            identify = {
                "op": 2,
                "d": {
                    "token": self.token,
                    "properties": {"$os": "Windows"},
                },
            }
            ws.send(json.dumps(identify))

            # Wait for READY
            ready = False
            for _ in range(10):
                resp = json.loads(ws.recv())
                if resp.get("t") == "READY":
                    ready = True
                    break
                if resp.get("op") == 9:  # Invalid session
                    ws.close()
                    return

            if not ready:
                ws.close()
                return

            # Stay online, send heartbeats until stopped
            while not self._stop.is_set():
                ws.send(json.dumps({"op": 1, "d": None}))
                self._stop.wait(heartbeat_interval)

            ws.close()
        except Exception:
            pass

def solve(sitekey, rqdata, user_agent, proxy=None):
    solver_key = config.get("data", {}).get("solver_api_key", "")
    solver = Solver(
        url="https://discord.com/register",
        sitekey=sitekey,
        rqdata=rqdata,
        user_agent=user_agent,
        proxy=proxy,
        api_key=solver_key
    )
    return solver.solve()

def reg(email, username, password, proxy=None, current_num=1):

    Log.proxy_header(current_num, proxy)
    Log.status(f"Using email: {email}")

    session = StealthSession()
    if proxy:
        proxy_url = f"http://{proxy}" if "://" not in proxy else proxy
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

    try:
        dcfduid, sdcfduid = fetch_cookies(session)
        fingerprint = get_fingerprint(session, dcfduid, sdcfduid)
    except Exception as e:
        Log.error(f"fingerprint failed")
        return

    build_num = get_build_number(proxy)
    super_props = build_super_properties(build_num)
    headers = build_headers(fingerprint, super_props)
    session.headers.update(headers)

    # Fake registration preflight (warms up session, mimics real user behavior)
    fake_user = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    fake_payload = {
        "fingerprint": fingerprint,
        "email": f"{fake_user}@outlook.com",
        "username": fake_user,
        "password": f"{fake_user}Ab1!@#",
        "date_of_birth": "1997-02-01",
        "consent": True,
    }

    try:
        fake_res = session.post("https://discord.com/api/v9/auth/register", json=fake_payload)
        fake_json = fake_res.json()
        if fake_res.status_code == 429:
            retry_after = fake_json.get("retry_after", 60)
            Log.waiting(f"rate limited, waiting {retry_after:.0f}s...")
            time.sleep(retry_after + 1)
    except Exception:
        pass

    register_payload = {
        "fingerprint": fingerprint,
        "email": email,
        "username": username,
        "password": password,
        "date_of_birth": "1997-02-01",
        "consent": True,
    }

    res = session.post("https://discord.com/api/v9/auth/register", json=register_payload)
    start_time = time.time()
    res_json = res.json()

    if res.status_code == 429:
        retry_after = res_json.get("retry_after", 60)
        Log.waiting(f"rate limited, waiting {retry_after:.0f}s...")
        time.sleep(retry_after + 1)
        res = session.post("https://discord.com/api/v9/auth/register", json=register_payload)
        res_json = res.json()

    captcha_sitekey = res_json.get("captcha_sitekey")
    captcha_rqdata = res_json.get("captcha_rqdata")
    captcha_rqtoken = res_json.get("captcha_rqtoken")
    captcha_session_id = res_json.get("captcha_session_id")

    if not captcha_sitekey or not captcha_rqdata:
        Log.error("no captcha")
        return

    Log.solving(email)
    cap_token, cookies = solve(captcha_sitekey, captcha_rqdata, USER_AGENT, proxy)

    if not cap_token:
        Log.captcha_failed()
        return

    if cookies:
        for k, v in cookies.items():
            session.cookies.set(k, v)
    solve_time = time.time() - start_time
    Log.captcha_solved(solve_time)

    session.headers.update({
        "x-captcha-key": cap_token,
        "x-captcha-rqtoken": captcha_rqtoken,
        "x-captcha-session-id": captcha_session_id,
    })

    response = None
    for attempt in range(3):
        try:
            response = session.post("https://discord.com/api/v9/auth/register", json=register_payload)
            break
        except Exception:
            if attempt < 2:
                time.sleep(1)
            else:
                return
    try:
        raw_text = response.text
        Log._log("[RESPONSE]", raw_text[:500], Fore.BLUE)
    except Exception as e:
        Log.error(f"Failed to read raw response: {e}")
        
    try:
        res_data = response.json()
    except Exception:
        Log.error("Response is not valid JSON")
        return

    if 'token' not in res_data:
        Log.error(f"no token, raw response: {res_data}")
        return

    auth_token = res_data['token']

    for h in ["x-captcha-key", "x-captcha-rqtoken", "x-captcha-session-id"]:
        session.headers.pop(h, None)

    session.headers.update({"authorization": auth_token})
    Log.generated(auth_token)

    # Start background gateway onliner — stays connected during entire verification flow
    onliner = BackgroundOnliner(auth_token)
    onliner.start()

    if not verification_enabled:
        pre_verify_status = check_token_status(session)
        save_account(email, password, auth_token, pre_verify_status)
        onliner.stop()
        return

    Log.waiting("waiting for verification email...")
    
    verify_url = mail_api.get_verify_url(email, 3, 120, proxy)
    if not verify_url:
        token_status = check_token_status(session)
        save_account(email, password, auth_token, token_status)
        onliner.stop()
        return

    try:
        click_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': f'"Chromium";v="{CHROME_VERSION}", "Google Chrome";v="{CHROME_VERSION}", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': USER_AGENT,
        }

        mail_token = None

        if "token=" in verify_url:
            mail_token = verify_url.split("token=")[-1].split("&")[0]

        if not mail_token:
            location = ""
            r1 = session.get(verify_url, headers=click_headers, allow_redirects=False)
            location = r1.headers.get("Location", "")

            if location:
                fragment = urlparse(location).fragment
                if fragment and "token=" in fragment:
                    mail_token = fragment.split("token=")[-1].split("&")[0]

            if not mail_token and location:
                r2 = session.get(location, headers=click_headers, allow_redirects=False)
                location2 = r2.headers.get("Location", "")
                if location2:
                    fragment2 = urlparse(location2).fragment
                    if fragment2 and "token=" in fragment2:
                        mail_token = fragment2.split("token=")[-1].split("&")[0]

        if not mail_token:
            token_status = check_token_status(session)
            save_account(email, password, auth_token, token_status)
            onliner.stop()
            return

    except Exception:
        token_status = check_token_status(session)
        save_account(email, password, auth_token, token_status)
        onliner.stop()
        return

    for h in ["x-captcha-key", "x-captcha-rqtoken", "x-captcha-session-id"]:
        session.headers.pop(h, None)

    time.sleep(random.uniform(1, 3))

    verify_res = session.post(
        "https://discord.com/api/v9/auth/verify",
        json={"token": mail_token}
    )
    verify_json = verify_res.json()

    if verify_json.get("captcha_sitekey"):
        Log.solving(email)
        verify_start = time.time()
        verify_cap_token, verify_cookies = solve(
            verify_json["captcha_sitekey"],
            verify_json.get("captcha_rqdata", ""),
            USER_AGENT,
            proxy
        )

        if not verify_cap_token:
            Log.captcha_failed()
            token_status = check_token_status(session)
            save_account(email, password, auth_token, token_status)
            onliner.stop()
            return

        verify_solve_time = time.time() - verify_start
        Log.captcha_solved(verify_solve_time)

        if verify_cookies:
            for k, v in verify_cookies.items():
                session.cookies.set(k, v)

        session.headers.update({
            "x-captcha-key": verify_cap_token,
            "x-captcha-rqtoken": verify_json.get("captcha_rqtoken", ""),
            "x-captcha-session-id": verify_json.get("captcha_session_id", ""),
        })

        verify_res = session.post(
            "https://discord.com/api/v9/auth/verify",
            json={"token": mail_token}
        )
        verify_json = verify_res.json()

    new_token = verify_json.get("token")
    if new_token:
        auth_token = new_token
        session.headers.update({"authorization": auth_token})
        Log.verified(auth_token)

    for h in ["x-captcha-key", "x-captcha-rqtoken", "x-captcha-session-id"]:
        session.headers.pop(h, None)

    token_status = check_token_status(session)
    Log.status(f"Verified: {token_status.upper()}")
    save_account(email, password, auth_token, token_status)
    onliner.stop()

def stats_updater():
    while True:
        time.sleep(2)
        with stats_lock:
            total = stats['total']
            gen = stats['generated']
            ver = stats['verified']
            cap_fail = stats['captcha_failed']
            cap_solved = stats['captcha_solved']
            locked = stats['locked']
            valid = stats['valid']
        gen_pct = (gen / total * 100) if total else 0
        ver_pct = (ver / total * 100) if total else 0
        cap_fail_pct = (cap_fail / total * 100) if total else 0
        cap_solved_pct = (cap_solved / total * 100) if total else 0
        locked_pct = (locked / total * 100) if total else 0
        valid_pct = (valid / total * 100) if total else 0
        current_time = datetime.now().strftime('%H:%M')
        title = f"{current_time} [STATS] Gen: {gen} ({gen_pct:.1f}%) | Ver: {ver} ({ver_pct:.1f}%) | CapFail: {cap_fail} ({cap_fail_pct:.1f}%) | CapSolved: {cap_solved} ({cap_solved_pct:.1f}%) | Locked: {locked} ({locked_pct:.1f}%) | Valid: {valid} ({valid_pct:.1f}%) | Total: {total}"
        ctypes.windll.kernel32.SetConsoleTitleW(title)

def display_banner():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    System.Clear()
    banner = """
                       ⠀⠀⠀⠀⠀⠀⠀⠀⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⡆
                       ⠀⠀⠀⠀⠀⠀⠀⠀⠘⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇      ● https://discord.gg/rezo
                       ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⣿⡿      ● https://rezotokens.mysellauth.com
                       ⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⣶⣶⣾⣿⣿⣿⣿⠟⠁      ● https://github.com/RezoSolver
                       ⠀⠀⠀⠀⠀⠀⠀⠀⣠⣿⣿⣿⠿⠿⠿⣿⣿⣿⡄      ● https://huzaif.online
                       ⠀⠀⠀⠀⠀⠀⠀⢠⣿⣿⡟⠀⠀⠀⠀⠈⢿⣿⣿⣆
                       ⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⡇⠀⠀⠀⠀⠀⠈⢿⣿⣿⣄
                       ⠀⠀⠀⠀⠀⠀⠀⢸⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀⠹⣿⣿⣦
                       ⠀⠀⠀⠀⠀⠀⠀⠈⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉
"""
    lines = [line for line in banner.split('\n') if line.strip() or '⠀' in line]
    
    max_len = max(len(line) for line in lines)
    
    padded_lines = [line.ljust(max_len, ' ') for line in lines]
    
    print("\n\n\n\n")
    
    for line in padded_lines:
        print(Colorate.Horizontal(Colors.purple_to_blue, Center.XCenter(line)))
        time.sleep(0.04)
        
    print("\n\n\n")

if __name__ == "__main__":
    display_banner()
    NUM_THREADS = int(input(Colorate.Horizontal(Colors.purple_to_blue, "Enter Number of Threads: ")))
    semaphore = threading.Semaphore(NUM_THREADS)

    stats_thread = threading.Thread(target=stats_updater, daemon=True)
    stats_thread.start()

    def worker(current_num):
        proxy = proxy_manager.pop_top()
        
        email = mail_api.create_account()
        if not email:
            Log.error("emails are not available")
            semaphore.release()
            return

        username = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        password = f"{username}REZO_SOLVERISBEST!@"

        try:
            reg(email, username, password, proxy, current_num)
        finally:
            semaphore.release()

    while True:
        semaphore.acquire()
        
        with gen_lock:
            gen_count += 1
            current_num = gen_count

        t = threading.Thread(target=worker, args=(current_num,), daemon=True)
        t.start()
