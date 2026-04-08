import re
import time
import logging
import threading
from datetime import datetime
import requests
from requests.auth import HTTPDigestAuth
import urllib3
import xml.etree.ElementTree as ET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFIGURASI ---
IP        = "192.168.68.101"
PORT      = 80
USE_HTTPS = False
USER      = "Nayakaws"
PASS      = "nayakaprtm2"

# Berapa detik tidak ada event "active" sebelum dianggap "motion berhenti"
INACTIVE_TIMEOUT = 3   # detik
RECONNECT_DELAY  = 3   # detik sebelum reconnect otomatis

# --- State global ---
# key: channel_id
# value: dict {'reported_active': bool, 'last_active_ts': float}
channel_state = {}
state_lock    = threading.Lock()


def parse_isapi_event(xml_data):
    try:
        xml_data_clean = re.sub(r'\sxmlns="[^"]+"', '', xml_data, count=1)
        root = ET.fromstring(xml_data_clean)

        event_time  = root.find('dateTime')
        event_type  = root.find('eventType')
        event_state = root.find('eventState')
        event_desc  = root.find('eventDescription')
        channel_id  = root.find('channelID')

        return {
            'timestamp':   event_time.text  if event_time  is not None else datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'type':        event_type.text  if event_type  is not None else 'Unknown',
            'state':       event_state.text if event_state is not None else 'Unknown',
            'description': event_desc.text  if event_desc  is not None else 'None',
            'channel':     channel_id.text  if channel_id  is not None else 'Unknown',
        }
    except Exception as e:
        return {'error': str(e), 'raw': xml_data}


def print_event(label, channel, timestamp, description=""):
    print(f"[{timestamp}]  {label}")
    print(f"  Channel  : {channel}")
    if description:
        print(f"  Deskripsi: {description}")
    print("-" * 80)


def watchdog_thread():
    """
    Thread terpisah yang terus memeriksa apakah channel yang sedang 'active'
    sudah tidak menerima event baru lebih dari INACTIVE_TIMEOUT detik.
    Jika iya, tandai sebagai 'inactive' dan cetak log berhenti.
    """
    while True:
        now = time.time()
        with state_lock:
            for ch, s in channel_state.items():
                if s['reported_active'] and (now - s['last_active_ts']) >= INACTIVE_TIMEOUT:
                    # Timeout — tandai inactive
                    s['reported_active'] = False
                    ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                    print_event("🟢 Human Undetected  (timeout)", ch, ts)
        time.sleep(0.5)


def stream_loop(session, url):
    """
    Buka koneksi ISAPI stream dan proses event satu per satu.
    Kembalikan False jika koneksi gagal (perlu reconnect).
    Kembalikan True jika berhenti karena KeyboardInterrupt.
    """
    try:
        response = session.get(url, stream=True, timeout=(10, 30), allow_redirects=True)

        if response.status_code == 401:
            print("⚠️  Digest Auth gagal, mencoba Basic Auth...")
            session.auth = (USER, PASS)
            response = session.get(url, stream=True, timeout=(10, 30), allow_redirects=True)

        if response.status_code != 200:
            print(f"❌ Gagal koneksi: HTTP {response.status_code}")
            return False

        print("\n✅ LISTENER AKTIF\n" + "-" * 80)

        payload_data = ""
        in_xml       = False

        for raw_line in response.iter_lines():
            if raw_line is None:
                continue
            decoded = raw_line.decode('utf-8', errors='ignore').strip()

            if "<EventNotificationAlert" in decoded:
                in_xml       = True
                payload_data = decoded
            elif in_xml:
                payload_data += decoded
                if "</EventNotificationAlert>" in decoded:
                    in_xml = False
                    event  = parse_isapi_event(payload_data)
                    payload_data = ""

                    if 'error' in event:
                        continue   # abaikan parse error, jangan spam

                    if event.get('type', '').upper() != 'VMD':
                        continue   # hanya proses VMD

                    ch    = event['channel']
                    state = event['state']
                    ts    = event['timestamp']
                    desc  = event['description']

                    with state_lock:
                        if ch not in channel_state:
                            channel_state[ch] = {'reported_active': False, 'last_active_ts': 0}

                        s = channel_state[ch]

                        if state == 'active':
                            # Perbarui waktu event terakhir (selalu)
                            s['last_active_ts'] = time.time()

                            # Hanya cetak jika belum dilaporkan active
                            if not s['reported_active']:
                                s['reported_active'] = True
                                print_event("🔴 Human Detected ", ch, ts, desc)

                        elif state == 'inactive':
                            # Kamera mengirim inactive secara eksplisit
                            if s['reported_active']:
                                s['reported_active'] = False
                                print_event("🟢 Human Undetected", ch, ts)

        # Stream ditutup oleh kamera
        print("\n⚠️  Stream ditutup oleh kamera.")
        return False

    except KeyboardInterrupt:
        return True   # sinyal berhenti

    except requests.exceptions.SSLError as e:
        print(f"\n❌ SSL Error: {e}")
        print("💡 Coba aktifkan USE_HTTPS=True dan PORT=443")
        return False

    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            ConnectionError) as e:
        print(f"\n❌ Koneksi terputus: {e}")
        return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def run_isapi_test():
    scheme = "https" if USE_HTTPS else "http"
    url    = f"{scheme}://{IP}:{PORT}/ISAPI/Event/notification/alertStream"

    print(f"Connecting to {url} via ISAPI...")
    print(f"(Motion dianggap berhenti setelah {INACTIVE_TIMEOUT}s tidak ada event)")
    print("(Tekan Ctrl+C untuk berhenti)\n")

    # Jalankan watchdog di background thread
    wd = threading.Thread(target=watchdog_thread, daemon=True)
    wd.start()

    attempt = 0
    while True:
        attempt += 1
        session = requests.Session()
        session.verify = False
        session.auth   = HTTPDigestAuth(USER, PASS)

        print(f"🔗 Koneksi attempt #{attempt}...")
        stop = stream_loop(session, url)

        if stop:
            break

        print(f"🔄 Reconnect dalam {RECONNECT_DELAY} detik...\n")
        try:
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            break

    print("\n⏹ Berhenti.")


if __name__ == "__main__":
    run_isapi_test()