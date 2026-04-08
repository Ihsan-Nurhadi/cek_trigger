import sys
import os
import time
import re
import logging
from datetime import datetime
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

# Konfigurasi logging dasar
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFIGURASI ---
IP = "192.168.68.101"
PORT = 80
USER = "Nayakaws"
PASS = "nayakaprtm2"

def parse_isapi_event(xml_data):
    try:
        
        xml_data_clean = re.sub(r'\sxmlns="[^"]+"', '', xml_data, count=1)
        root = ET.fromstring(xml_data_clean)
        
        event_time = root.find('dateTime')
        event_type = root.find('eventType')
        event_state = root.find('eventState')
        event_desc = root.find('eventDescription')
        channel_id = root.find('channelID')
        
        
        data = {
            'timestamp': event_time.text if event_time is not None else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': event_type.text if event_type is not None else 'Unknown',
            'state': event_state.text if event_state is not None else 'Unknown',
            'description': event_desc.text if event_desc is not None else 'None',
            'channel': channel_id.text if channel_id is not None else 'Unknown'
        }
        return data
    except Exception as e:
        return {'error': str(e), 'raw': xml_data}

def run_isapi_test():
    url = f"http://{IP}:{PORT}/ISAPI/Event/notification/alertStream"
    
    print(f"Connecting to {url} via ISAPI...")
    
    try:
        
        response = requests.get(url, auth=HTTPDigestAuth(USER, PASS), stream=True, timeout=(10, None))
        
        
        if response.status_code == 401:
            print("Digest Auth gagal, mencoba Basic Auth...")
            response = requests.get(url, auth=(USER, PASS), stream=True, timeout=(10, None))
            
        if response.status_code != 200:
            print(f"❌ Gagal koneksi: HTTP {response.status_code}")
            return

        print("\n✅ LISTENER AKTIF - Menampilkan Log Event dari ISAPI...\n")
        print("-" * 80)
        
        payload_data = ""
        in_xml = False
        
       
        for line in response.iter_lines():
            if not line:
                continue
                
            decoded_line = line.decode('utf-8', errors='ignore').strip()
            
            
            if "<EventNotificationAlert" in decoded_line:
                in_xml = True
                payload_data = decoded_line
            elif in_xml:
                payload_data += decoded_line
                if "</EventNotificationAlert>" in decoded_line:
                    in_xml = False
                    
                    event = parse_isapi_event(payload_data)
                    
                    if 'error' in event:
                        print(f"Error parse event: {event['error']}")
                        print(f"Raw Data: {event['raw']}")
                    elif event.get('type', '').upper() == 'VMD':
                        print(f"[{event['timestamp']}]")
                        print(f"Event Type : {event['type']}")
                        print(f"Event State: {event['state']}")
                        print(f"Channel    : {event['channel']}")
                        print(f"Deskripsi  : {event['description']}")
                        print("-" * 80)
                        
                    payload_data = ""
                    
    except requests.exceptions.Timeout:
        print("❌ Koneksi Timeout. Pastikan IP dan Port benar.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error koneksi stream: {e}")
    except KeyboardInterrupt:
        print("\n⏹ Berhenti.")

if __name__ == "__main__":
    run_isapi_test()