import re
import time
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests
from requests.auth import HTTPDigestAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────────
IP        = "192.168.68.101"
PORT      = 80
USE_HTTPS = False
USER      = "Nayakaws"
PASS      = "nayakaprtm2"

# Zona waktu lokal: WIB = UTC+7
LOCAL_TZ = timezone(timedelta(hours=7))

# Detik tanpa event "active" sebelum dianggap gerakan berhenti (fallback)
INACTIVE_TIMEOUT = 5    # detik — sedikit lebih toleran dari versi lama

# Interval polling log kamera untuk verifikasi motionStart/Stop
LOG_POLL_INTERVAL = 10  # detik

# Delay sebelum reconnect otomatis
RECONNECT_DELAY = 3     # detik

# ─────────────────────────────────────────────
#  STATE GLOBAL
# ─────────────────────────────────────────────
# key: channel_id (str)
# value: {
#   'reported_active' : bool,
#   'last_active_ts'  : float  (time.time()),
#   'start_time_local': str    (waktu lokal saat mulai terdeteksi)
# }
channel_state: dict = {}
state_lock = threading.Lock()


# ─────────────────────────────────────────────
#  HELPER: KONVERSI WAKTU
# ─────────────────────────────────────────────
def utc_str_to_local(utc_str: str) -> str:
    """
    Konversi string UTC murni (misal dari logSearch kamera)
    ke waktu lokal WIB. Digunakan HANYA untuk endpoint logSearch.
    """
    try:
        utc_str_clean = utc_str.rstrip('Z')
        dt_utc = datetime.fromisoformat(utc_str_clean).replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(LOCAL_TZ)
        return dt_local.strftime('%Y-%m-%d %H:%M:%S WIB')
    except Exception:
        return utc_str


def camera_ts_reformat(cam_ts: str) -> str:
    """
    Reformat timestamp dari alertStream tanpa menggeser timezone.
    Kamera Hikvision mengirim dateTime di alertStream sudah dalam
    waktu LOKAL (bukan UTC murni), sehingga tidak boleh ditambah +7.
    Hanya ubah format dari 'YYYY-MM-DDTHH:MM:SS' ke 'YYYY-MM-DD HH:MM:SS WIB'.
    """
    try:
        clean = cam_ts.rstrip('Z')
        dt = datetime.fromisoformat(clean)
        return dt.strftime('%Y-%m-%d %H:%M:%S WIB')
    except Exception:
        return cam_ts


def now_local_str() -> str:
    """Waktu lokal sekarang sebagai string."""
    return datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S WIB')


# ─────────────────────────────────────────────
#  HELPER: PARSE XML EVENT dari alertStream
# ─────────────────────────────────────────────
def parse_alert_event(xml_data: str) -> dict:
    """
    Parse satu blok <EventNotificationAlert> dari ISAPI alertStream.
    Return dict dengan key: timestamp, type, state, description, channel.
    Return dict dengan key 'error' jika gagal.
    """
    try:
        # Hapus deklarasi namespace agar ET tidak komplain
        clean = re.sub(r'\sxmlns="[^"]+"', '', xml_data, count=1)
        root  = ET.fromstring(clean)

        def find_text(tag):
            el = root.find(tag)
            return el.text.strip() if (el is not None and el.text) else None

        return {
            'timestamp'  : find_text('dateTime') or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'type'       : find_text('eventType') or 'Unknown',
            'state'      : find_text('eventState') or 'Unknown',
            'description': find_text('eventDescription') or '',
            'channel'    : find_text('channelID') or '?',
        }
    except Exception as e:
        return {'error': str(e)}


# ─────────────────────────────────────────────
#  HELPER: QUERY LOG KAMERA (verifikasi)
# ─────────────────────────────────────────────
def query_camera_log(session: requests.Session, minutes_back: int = 2) -> list[dict]:
    """
    Query endpoint ISAPI logSearch untuk mendapatkan motionStart/motionStop
    yang dicatat kamera dalam N menit terakhir.

    Return list of dict: [{'event': 'motionStart'|'motionStop', 'time_local': str}]
    """
    scheme    = "https" if USE_HTTPS else "http"
    log_url   = f"{scheme}://{IP}:{PORT}/ISAPI/ContentMgmt/logSearch"

    now_utc   = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(minutes=minutes_back)

    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
  <searchID>log-motion-check</searchID>
  <timeSpanList>
    <timeSpan>
      <startTime>{start_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}</startTime>
      <endTime>{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}</endTime>
    </timeSpan>
  </timeSpanList>
  <maxResults>20</maxResults>
  <searchResultPosition>0</searchResultPosition> 
  <logFilter>
    <major>ALARM</major>
  </logFilter>
</CMSearchDescription>"""

    try:
        resp = session.post(log_url, data=body, timeout=5,
                            headers={'Content-Type': 'application/xml'})
        if resp.status_code != 200:
            return []

        clean  = re.sub(r'\sxmlns="[^"]+"', '', resp.text, count=1)
        # Bersihkan semua namespace prefix juga
        clean  = re.sub(r'<(/?)[\w]+:', r'<\1', clean)
        root   = ET.fromstring(clean)

        results = []
        for item in root.iter('searchMatchItem'):
            meta_el   = item.find('.//metaId')
            time_el   = item.find('.//StartDateTime')
            if meta_el is None or time_el is None:
                continue
            meta_text = meta_el.text or ''
            if 'motionStart' in meta_text:
                results.append({'event': 'motionStart', 'time_local': utc_str_to_local(time_el.text)})
            elif 'motionStop' in meta_text:
                results.append({'event': 'motionStop',  'time_local': utc_str_to_local(time_el.text)})

        return results

    except Exception:
        return []


# ─────────────────────────────────────────────
#  PRINTER
# ─────────────────────────────────────────────
DIVIDER = "─" * 72

def print_motion_start(channel: str, time_local: str, description: str = ""):
    print(f"\n{'▶ MOTION DETECTED':^72}")
    print(DIVIDER)
    print(f"  Waktu    : {time_local}")
    print(f"  Channel  : {channel}")
    if description:
        print(f"  Deskripsi: {description}")
    print(DIVIDER)

def print_motion_stop(channel: str, time_local: str, source: str = "camera"):
    label = "◀ MOTION STOPPED"
    note  = f"(sumber: {source})"
    print(f"\n{label:^72}")
    print(DIVIDER)
    print(f"  Waktu    : {time_local}")
    print(f"  Channel  : {channel}")
    print(f"  Catatan  : {note}")
    print(DIVIDER)

def print_log_verify(entries: list[dict]):
    """Tampilkan ringkasan log kamera saat polling."""
    if not entries:
        return
    print(f"\n  [LOG KAMERA] {len(entries)} event motion tercatat:")
    for e in entries:
        icon = "▶" if e['event'] == 'motionStart' else "◀"
        print(f"    {icon} {e['event']:12s}  {e['time_local']}")


# ─────────────────────────────────────────────
#  WATCHDOG THREAD
#  Fallback: jika kamera tidak kirim "inactive",
#  tandai stop setelah INACTIVE_TIMEOUT detik.
# ─────────────────────────────────────────────
def watchdog_thread():
    while True:
        now = time.time()
        with state_lock:
            for ch, s in channel_state.items():
                if s['reported_active']:
                    elapsed = now - s['last_active_ts']
                    if elapsed >= INACTIVE_TIMEOUT:
                        s['reported_active'] = False
                        print_motion_stop(ch, now_local_str(), source="timeout fallback")
        time.sleep(0.5)


# ─────────────────────────────────────────────
#  LOG POLL THREAD
#  Verifikasi berkala dengan log kamera asli.
# ─────────────────────────────────────────────
def log_poll_thread(session_ref: list):
    """
    Setiap LOG_POLL_INTERVAL detik, query log kamera dan tampilkan
    ringkasan event motion yang baru saja dicatat.
    session_ref: list berisi satu element (session aktif), agar bisa diperbarui.
    """
    while True:
        time.sleep(LOG_POLL_INTERVAL)
        sess = session_ref[0]
        if sess is None:
            continue
        entries = query_camera_log(sess, minutes_back=2)
        if entries:
            print_log_verify(entries)


# ─────────────────────────────────────────────
#  STREAM LOOP
# ─────────────────────────────────────────────
def stream_loop(session: requests.Session, url: str) -> bool:
    """
    Buka ISAPI alertStream dan proses event motion.
    Return True  → berhenti (KeyboardInterrupt).
    Return False → koneksi putus, perlu reconnect.
    """
    try:
        resp = session.get(url, stream=True, timeout=(10, None), allow_redirects=True)

        # Fallback ke Basic Auth jika Digest gagal
        if resp.status_code == 401:
            print("  ⚠️  Digest Auth gagal, mencoba Basic Auth...")
            session.auth = (USER, PASS)
            resp = session.get(url, stream=True, timeout=(10, None), allow_redirects=True)

        if resp.status_code != 200:
            print(f"  ❌ Gagal koneksi HTTP {resp.status_code}")
            return False

        print(f"\n  ✅ Stream terhubung — mendengarkan motion events...\n{DIVIDER}")

        buffer = ""
        in_xml = False

        for raw_line in resp.iter_lines():
            if raw_line is None:
                continue
            line = raw_line.decode('utf-8', errors='ignore').strip()

            # ── Kumpulkan blok XML ──
            if "<EventNotificationAlert" in line:
                in_xml = True
                buffer = line
            elif in_xml:
                buffer += line
                if "</EventNotificationAlert>" in line:
                    in_xml = False
                    event  = parse_alert_event(buffer)
                    buffer = ""

                    if 'error' in event:
                        continue  # abaikan parse error

                    # ── Hanya proses VMD (Video Motion Detection) ──
                    if event['type'].upper() != 'VMD':
                        continue

                    ch     = event['channel']
                    state  = event['state'].lower()     # 'active' / 'inactive'
                    # Gunakan waktu sistem saat event DITERIMA — paling akurat
                    # karena kamera alertStream mengirim dateTime dalam waktu
                    # lokal (bukan UTC), sehingga tidak bisa dikonversi langsung.
                    # camera_ts_reformat() tersedia jika ingin pakai waktu kamera:
                    #   ts_loc = camera_ts_reformat(event['timestamp'])
                    ts_loc = now_local_str()
                    desc   = event['description']

                    with state_lock:
                        if ch not in channel_state:
                            channel_state[ch] = {
                                'reported_active': False,
                                'last_active_ts' : 0.0,
                                'start_time_local': ''
                            }

                        s = channel_state[ch]

                        if state == 'active':
                            # Selalu perbarui timestamp agar watchdog tidak
                            # salah trigger stop selama gerakan masih berlanjut
                            s['last_active_ts'] = time.time()

                            if not s['reported_active']:
                                s['reported_active']   = True
                                s['start_time_local']  = ts_loc
                                print_motion_start(ch, ts_loc, desc)

                        elif state == 'inactive':
                            # Kamera secara eksplisit menyatakan gerakan berhenti
                            # → ini lebih akurat daripada timeout
                            if s['reported_active']:
                                s['reported_active'] = False
                                print_motion_stop(ch, ts_loc, source="camera signal")

        print(f"\n  ⚠️  Stream ditutup oleh kamera.")
        return False

    except KeyboardInterrupt:
        return True

    except requests.exceptions.SSLError as e:
        print(f"\n  ❌ SSL Error: {e}")
        return False

    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout) as e:
        print(f"\n  ❌ Koneksi terputus: {e}")
        return False

    except Exception as e:
        print(f"\n  ❌ Error tidak terduga: {e}")
        return False


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    scheme = "https" if USE_HTTPS else "http"
    url    = f"{scheme}://{IP}:{PORT}/ISAPI/Event/notification/alertStream"

    print("=" * 72)
    print("  HIKVISION MOTION DETECTOR  (upgraded)")
    print("=" * 72)
    print(f"  Target   : {url}")
    print(f"  Stop logic: camera signal DULU, fallback timeout {INACTIVE_TIMEOUT}s")
    print(f"  Log verify: setiap {LOG_POLL_INTERVAL} detik")
    print(f"  Timezone : WIB (UTC+7)")
    print("  Tekan Ctrl+C untuk berhenti")
    print("=" * 72)

    # Referensi session untuk log poll thread
    session_ref = [None]

    # Jalankan watchdog
    threading.Thread(target=watchdog_thread, daemon=True).start()

    # Jalankan log poller
    threading.Thread(target=log_poll_thread, args=(session_ref,), daemon=True).start()

    attempt = 0
    while True:
        attempt += 1
        session = requests.Session()
        session.verify = False
        session.auth   = HTTPDigestAuth(USER, PASS)
        session_ref[0] = session

        print(f"\n  🔗 Koneksi attempt #{attempt}...")
        stop = stream_loop(session, url)

        if stop:
            break

        print(f"  🔄 Reconnect dalam {RECONNECT_DELAY} detik...")
        try:
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            break

    print("\n  ⏹  Berhenti.\n")


if __name__ == "__main__":
    main()
