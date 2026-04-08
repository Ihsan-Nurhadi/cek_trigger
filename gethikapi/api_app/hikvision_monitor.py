"""
hikvision_monitor.py
====================
Adaptasi dari test_hikvision_motion.py untuk berjalan sebagai
background service di dalam Django.

Menyediakan:
  - HikvisionMonitor  : thread per site kamera
  - MonitorManager    : singleton untuk spawn/stop semua monitor
  - SSE broadcast     : notifikasi dikirim ke semua client SSE yang terhubung
"""

import re
import time
import threading
import queue
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests
from requests.auth import HTTPDigestAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────────────────────
#  KONSTANTA
# ─────────────────────────────────────────────────────────────
LOCAL_TZ         = timezone(timedelta(hours=7))   # WIB = UTC+7
INACTIVE_TIMEOUT = 5       # detik — fallback jika kamera tidak kirim 'inactive'
RECONNECT_DELAY  = 3       # detik
WATCHDOG_TICK    = 0.5     # detik

# ─────────────────────────────────────────────────────────────
#  SSE BROADCAST
#  Semua client SSE yang terhubung dimasukkan ke sse_clients.
#  Saat ada event baru, semua queue di-push.
# ─────────────────────────────────────────────────────────────
sse_clients: list[queue.Queue] = []
sse_lock = threading.Lock()


def sse_broadcast(data: dict):
    """Kirim dict ke semua SSE client yang sedang terhubung."""
    import json
    payload = f"data: {json.dumps(data)}\n\n"
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


def register_sse_client() -> queue.Queue:
    q = queue.Queue(maxsize=50)
    with sse_lock:
        sse_clients.append(q)
    return q


def unregister_sse_client(q: queue.Queue):
    with sse_lock:
        if q in sse_clients:
            sse_clients.remove(q)


# ─────────────────────────────────────────────────────────────
#  HELPER
# ─────────────────────────────────────────────────────────────
def now_local_str() -> str:
    return datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S WIB')


def parse_alert_event(xml_data: str) -> dict:
    try:
        clean = re.sub(r'\sxmlns="[^"]+"', '', xml_data, count=1)
        root  = ET.fromstring(clean)

        def find_text(tag):
            el = root.find(tag)
            return el.text.strip() if (el is not None and el.text) else None

        return {
            'timestamp'  : find_text('dateTime') or '',
            'type'       : find_text('eventType') or 'Unknown',
            'state'      : find_text('eventState') or 'Unknown',
            'description': find_text('eventDescription') or '',
            'channel'    : find_text('channelID') or '1',
        }
    except Exception as e:
        return {'error': str(e)}


# ─────────────────────────────────────────────────────────────
#  HIKVISION MONITOR  (1 instance = 1 thread = 1 kamera site)
# ─────────────────────────────────────────────────────────────
class HikvisionMonitor:
    def __init__(self, site_id: int, name: str, ip: str, port: int,
                 username: str, password: str):
        self.site_id  = site_id
        self.name     = name
        self.ip       = ip
        self.port     = port
        self.username = username
        self.password = password

        self._stop_event = threading.Event()
        self._channel_state: dict = {}   # {ch: {reported_active, last_active_ts}}
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._watchdog: threading.Thread | None = None

    # ── public ──────────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True,
            name=f'hik-monitor-{self.site_id}'
        )
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True,
            name=f'hik-watchdog-{self.site_id}'
        )
        self._thread.start()
        self._watchdog.start()

    def stop(self):
        self._stop_event.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── internal ─────────────────────────────────────────────
    def _run(self):
        scheme = 'http'
        url = f'{scheme}://{self.ip}:{self.port}/ISAPI/Event/notification/alertStream'
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            try:
                self._stream_loop(url)
            except Exception:
                pass
            if self._stop_event.is_set():
                break
            self._stop_event.wait(RECONNECT_DELAY)

    def _stream_loop(self, url: str):
        session = requests.Session()
        session.verify = False
        session.auth   = HTTPDigestAuth(self.username, self.password)

        try:
            resp = session.get(url, stream=True, timeout=(10, None))
            if resp.status_code == 401:
                session.auth = (self.username, self.password)
                resp = session.get(url, stream=True, timeout=(10, None))
            if resp.status_code != 200:
                return

            buffer = ''
            in_xml = False

            for raw_line in resp.iter_lines():
                if self._stop_event.is_set():
                    break
                if raw_line is None:
                    continue
                line = raw_line.decode('utf-8', errors='ignore').strip()

                if '<EventNotificationAlert' in line:
                    in_xml = True
                    buffer = line
                elif in_xml:
                    buffer += line
                    if '</EventNotificationAlert>' in line:
                        in_xml = False
                        event  = parse_alert_event(buffer)
                        buffer = ''
                        if 'error' not in event:
                            self._handle_event(event)

        except Exception:
            pass
        finally:
            session.close()

    def _handle_event(self, event: dict):
        if event.get('type', '').upper() != 'VMD':
            return

        ch    = event['channel']
        state = event['state'].lower()
        ts    = now_local_str()

        with self._state_lock:
            if ch not in self._channel_state:
                self._channel_state[ch] = {
                    'reported_active': False,
                    'last_active_ts' : 0.0,
                }
            s = self._channel_state[ch]

            if state == 'active':
                s['last_active_ts'] = time.time()
                if not s['reported_active']:
                    s['reported_active'] = True
                    self._save_event(ch, 'motion_start', ts)

            elif state == 'inactive':
                if s['reported_active']:
                    s['reported_active'] = False
                    self._save_event(ch, 'motion_stop', ts)

    def _watchdog_loop(self):
        while not self._stop_event.is_set():
            now = time.time()
            with self._state_lock:
                for ch, s in self._channel_state.items():
                    if s['reported_active']:
                        if (now - s['last_active_ts']) >= INACTIVE_TIMEOUT:
                            s['reported_active'] = False
                            self._save_event(ch, 'motion_stop', now_local_str())
            self._stop_event.wait(WATCHDOG_TICK)

    def _save_event(self, channel: str, event_type: str, ts_str: str):
        """Simpan ke database Django dan broadcast ke SSE clients."""
        try:
            # Import di dalam method untuk menghindari circular import
            import django
            from django.apps import apps
            MotionNotification = apps.get_model('api_app', 'MotionNotification')
            CameraSite         = apps.get_model('api_app', 'CameraSite')

            site_obj = CameraSite.objects.filter(pk=self.site_id).first()
            notif = MotionNotification(
                site=site_obj,
                site_name=self.name,
                channel=channel,
                event_type=event_type,
            )
            notif.save()  # auto-cap 20 triggered di save()

            # Broadcast ke SSE
            sse_broadcast({
                'id'        : notif.id,
                'site_name' : self.name,
                'channel'   : channel,
                'event_type': event_type,
                'timestamp' : ts_str,
                'is_read'   : False,
            })

        except Exception as e:
            # Jangan crash thread jika DB error
            print(f'[HikvisionMonitor] DB save error: {e}')


# ─────────────────────────────────────────────────────────────
#  MONITOR MANAGER  (singleton)
# ─────────────────────────────────────────────────────────────
class MonitorManager:
    _instance: 'MonitorManager | None' = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._monitors: dict[int, HikvisionMonitor] = {}
                    cls._instance._mgr_lock = threading.Lock()
        return cls._instance

    # ── public API ───────────────────────────────────────────
    def start_all(self):
        """Dipanggil dari apps.ready() — start semua active site."""
        try:
            from django.apps import apps
            CameraSite = apps.get_model('api_app', 'CameraSite')
            for site in CameraSite.objects.filter(is_active=True):
                self.start_site(site)
        except Exception as e:
            print(f'[MonitorManager] start_all error: {e}')

    def start_site(self, site):
        with self._mgr_lock:
            sid = site.id
            if sid in self._monitors and self._monitors[sid].is_running():
                return  # sudah jalan
            monitor = HikvisionMonitor(
                site_id=sid,
                name=site.name,
                ip=site.ip,
                port=site.port,
                username=site.username,
                password=site.password,
            )
            monitor.start()
            self._monitors[sid] = monitor
            print(f'[MonitorManager] Started monitor for site: {site.name} ({site.ip})')

    def stop_site(self, site_id: int):
        with self._mgr_lock:
            monitor = self._monitors.pop(site_id, None)
            if monitor:
                monitor.stop()
                print(f'[MonitorManager] Stopped monitor site_id={site_id}')

    def restart_site(self, site):
        self.stop_site(site.id)
        time.sleep(0.5)
        self.start_site(site)

    def status(self) -> dict:
        with self._mgr_lock:
            return {
                sid: m.is_running()
                for sid, m in self._monitors.items()
            }


# Singleton instance
monitor_manager = MonitorManager()
