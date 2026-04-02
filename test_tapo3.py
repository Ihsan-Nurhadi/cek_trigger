import sys
import os
import time
import re
import logging
from datetime import datetime
from onvif import ONVIFCamera
from zeep import Client
from zeep.wsse.username import UsernameToken

# Konfigurasi logging dasar
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFIGURASI ---
IP = "192.168.68.101"
PORT = 80
USER = "Nayakaws"
PASS = "nayakaprtm2"

def extract_simple_items_from_xml(element):
    result = {}
    namespaces = {'tt': 'http://www.onvif.org/ver10/schema'}
    simple_items = element.findall('.//tt:SimpleItem', namespaces)
    for item in simple_items:
        name = item.get('Name')
        value = item.get('Value')
        if name: result[name] = value
    return result

def parse_tapo_event(message):
    try:
        event_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'topic': None,
            'data': {}
        }
        
        if hasattr(message, 'Topic'):
            topic_obj = message.Topic
            event_data['topic'] = str(topic_obj._value_1) if hasattr(topic_obj, '_value_1') else str(topic_obj)
        
        if hasattr(message, 'Message'):
            msg_obj = message.Message
            if hasattr(msg_obj, '_value_1') and msg_obj._value_1 is not None:
                xml_element = msg_obj._value_1
                ns = {'tt': 'http://www.onvif.org/ver10/schema'}
                data_elem = xml_element.find('tt:Data', ns)
                if data_elem is not None:
                    event_data['data'] = extract_simple_items_from_xml(data_elem)

        return event_data
    except Exception as e:
        return {'error': str(e)}

def run_simple_test():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    wsdl_path = os.path.join(current_dir, 'wsdl')
    
    if not os.path.exists(wsdl_path):
        print(f"❌ Folder WSDL tidak ditemukan di: {wsdl_path}")
        return

    try:
        print(f"Connecting to {IP}:{PORT}...")
        cam = ONVIFCamera(IP, PORT, USER, PASS, wsdl_dir=wsdl_path)
        event_service = cam.create_events_service()
        subscription_response = event_service.CreatePullPointSubscription()
        
        try: raw_url = subscription_response.SubscriptionReference.Address._value_1
        except: raw_url = subscription_response.SubscriptionReference.Address

        final_url = raw_url
        if f":{PORT}/" not in raw_url:
            final_url = re.sub(r':\d+/', f':{PORT}/', raw_url)

        events_wsdl_file = os.path.join(wsdl_path, 'events.wsdl')
        binding_name = '{http://www.onvif.org/ver10/events/wsdl}PullPointSubscriptionBinding'
        token = UsernameToken(USER, PASS, use_digest=True)
        pullpoint = Client(wsdl=events_wsdl_file, transport=cam.transport, wsse=token).create_service(binding_name, final_url)

        print("\n✅ LISTENER AKTIF - Filter Spam Aktif. Menunggu perubahan event...\n")
        print("-" * 80)
        
        last_state = {}

        while True:
            try:
                response = pullpoint.PullMessages(Timeout='PT5S', MessageLimit=10)
                
                if hasattr(response, 'NotificationMessage'):
                    messages = response.NotificationMessage
                    if not isinstance(messages, list): messages = [messages]
                    
                    for msg in messages:
                        event = parse_tapo_event(msg)
                        if 'error' in event:
                            print(f"Error parsing event: {event['error']}")
                            continue
                        
                        topic = event['topic']
                        data_str = str(event['data'])
                        
                        # Hanya memproses jika Topic dan Data berbeda dengan yang terakhir kali dicatat
                        if topic not in last_state or last_state[topic] != data_str:
                            last_state[topic] = data_str # Simpan state yang baru
                            
                            # Filter opsional: abaikan log rutin seperti ProcessorUsage jika tidak penting
                            if "ProcessorUsage" not in topic:
                                print(f"[{event['timestamp']}]")
                                print(f"Topic: {topic}")
                                print(f"Data : {event['data']}")
                                print("-" * 80)
                
                time.sleep(0.1)
                
            except Exception as e:
                error_msg = str(e).lower()
                if "timeout" not in error_msg and "no messages" not in error_msg:
                    print(f"Iteration Error: {e}")
                time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n� Berhenti.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_simple_test()