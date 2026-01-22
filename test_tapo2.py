import sys
import os
import time
import re
import logging
import json
from datetime import datetime
from lxml import etree
from onvif import ONVIFCamera
from zeep import Client
from zeep.wsse.username import UsernameToken


# Konfigurasi logging yang lebih bersih
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Matikan debug zeep agar tidak berisik
logging.getLogger('zeep').setLevel(logging.WARNING)

# --- KONFIGURASI ---
IP = "192.168.68.105"
PORT = 2020
USER = "nayakapratama"
PASS = "nayakapratama"


def zeep_to_dict(obj, include_private=True):
    """Konversi objek Zeep ke dictionary"""
    if obj is None:
        return None
    
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    if isinstance(obj, datetime):
        return obj.isoformat()
    
    if isinstance(obj, list):
        return [zeep_to_dict(item, include_private) for item in obj]
    
    if hasattr(obj, '__dict__'):
        result = {}
        for key, value in obj.__dict__.items():
            # Include private attributes jika diminta
            if include_private or not key.startswith('_'):
                result[key] = zeep_to_dict(value, include_private)
        return result
    
    return str(obj)


def parse_xml_element(element):
    """Parse lxml Element menjadi dictionary"""
    result = {}
    
    # Ambil attributes
    for key, value in element.attrib.items():
        # Hilangkan namespace prefix
        key_name = key.split('}')[-1] if '}' in key else key
        result[key_name] = value
    
    # Ambil child elements
    children = {}
    for child in element:
        # Hilangkan namespace dari tag
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        # Jika child punya children, parse rekursif
        if len(child) > 0:
            child_data = parse_xml_element(child)
            if tag in children:
                # Jika sudah ada, buat jadi list
                if not isinstance(children[tag], list):
                    children[tag] = [children[tag]]
                children[tag].append(child_data)
            else:
                children[tag] = child_data
        else:
            # Leaf node, ambil text atau attributes
            if child.text and child.text.strip():
                value = child.text.strip()
            else:
                value = dict(child.attrib)
            
            if tag in children:
                if not isinstance(children[tag], list):
                    children[tag] = [children[tag]]
                children[tag].append(value)
            else:
                children[tag] = value
    
    result.update(children)
    
    # Jika element punya text dan tidak punya children
    if element.text and element.text.strip() and len(element) == 0:
        return element.text.strip()
    
    return result if result else None


def extract_simple_items_from_xml(element):
    """Ekstrak SimpleItem dari XML Element"""
    result = {}
    
    # Namespace ONVIF
    namespaces = {
        'tt': 'http://www.onvif.org/ver10/schema'
    }
    
    # Cari semua SimpleItem
    simple_items = element.findall('.//tt:SimpleItem', namespaces)
    
    for item in simple_items:
        name = item.get('Name')
        value = item.get('Value')
        if name:
            result[name] = value
    
    return result


def parse_tapo_event(message):
    """Parse event message dari Tapo dan ekstrak informasi penting"""
    try:
        event_data = {
            'timestamp': None,
            'topic': None,
            'event_type': None,
            'is_people_detected': False,
            'source': {},
            'data': {},
            'property_operation': None
        }
        
        # Ekstrak Topic
        if hasattr(message, 'Topic'):
            topic_obj = message.Topic
            if hasattr(topic_obj, '_value_1'):
                event_data['topic'] = str(topic_obj._value_1)
            else:
                event_data['topic'] = str(topic_obj)
            
            # Deteksi tipe event berdasarkan topic
            if 'PeopleDetector/People' in event_data['topic']:
                event_data['event_type'] = 'People Detection'
            elif 'MotionDetector' in event_data['topic']:
                event_data['event_type'] = 'Motion Detection'
            elif 'CellMotionDetector' in event_data['topic']:
                event_data['event_type'] = 'Cell Motion Detection'
            else:
                event_data['event_type'] = 'Unknown Event'
        
        # Ekstrak Message content - INI ADALAH XML ELEMENT!
        if hasattr(message, 'Message'):
            msg_obj = message.Message
            
            # Akses _value_1 yang adalah lxml Element
            if hasattr(msg_obj, '_value_1') and msg_obj._value_1 is not None:
                xml_element = msg_obj._value_1
                
                # Namespace ONVIF
                ns = {'tt': 'http://www.onvif.org/ver10/schema'}
                
                # Ekstrak PropertyOperation
                prop_op = xml_element.get('PropertyOperation')
                if prop_op:
                    event_data['property_operation'] = prop_op
                
                # Ekstrak UtcTime
                utc_time = xml_element.get('UtcTime')
                if utc_time:
                    event_data['timestamp'] = utc_time
                
                # Ekstrak Source
                source_elem = xml_element.find('tt:Source', ns)
                if source_elem is not None:
                    event_data['source'] = extract_simple_items_from_xml(source_elem)
                
                # Ekstrak Data
                data_elem = xml_element.find('tt:Data', ns)
                if data_elem is not None:
                    event_data['data'] = extract_simple_items_from_xml(data_elem)
                    
                    # Cek apakah terdeteksi people
                    if event_data['data'].get('IsPeople') == 'true':
                        event_data['is_people_detected'] = True
                    elif event_data['data'].get('State') == 'true':
                        event_data['is_people_detected'] = True
        
        return event_data
        
    except Exception as e:
        logging.error(f"Error parsing event: {e}")
        import traceback
        traceback.print_exc()
        return {
            'error': str(e), 
            'message': 'Failed to parse event'
        }


def get_tapo_proof_data():
    print("\n" + "="*60)
    print("🎥 TAPO EVENT MONITOR - XML to JSON Converter v2")
    print("="*60)
    print(f"📡 Kamera: {IP}:{PORT}")
    print(f"👤 User: {USER}")
    print("="*60 + "\n")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    wsdl_path = os.path.join(current_dir, 'wsdl')
    
    if not os.path.exists(wsdl_path):
        print(f"❌ [ERROR] Folder wsdl tidak ditemukan di {wsdl_path}!")
        return

    try:
        # 1. KONEKSI AWAL
        print(f"🔌 Menghubungkan ke kamera...")
        cam = ONVIFCamera(IP, PORT, USER, PASS, wsdl_dir=wsdl_path)
        
        # 2. SUBSCRIBE
        print("📝 Membuat subscription...")
        event_service = cam.create_events_service()
        subscription_response = event_service.CreatePullPointSubscription()
        
        # 3. PERBAIKI ALAMAT
        try:
            raw_url = subscription_response.SubscriptionReference.Address._value_1
        except:
            raw_url = subscription_response.SubscriptionReference.Address

        final_url = raw_url
        if f":{PORT}/" not in raw_url:
            final_url = re.sub(r':\d+/', f':{PORT}/', raw_url)
            print(f"🔧 URL diperbaiki: {final_url}")

        # 4. BUAT KONEKSI SECURE
        print("🔐 Membuat koneksi secure (WSSE)...")
        events_wsdl_file = os.path.join(wsdl_path, 'events.wsdl')
        binding_name = '{http://www.onvif.org/ver10/events/wsdl}PullPointSubscriptionBinding'
        
        token = UsernameToken(USER, PASS, use_digest=True)
        pullpoint_client = Client(wsdl=events_wsdl_file, transport=cam.transport, wsse=token)
        pullpoint = pullpoint_client.create_service(binding_name, final_url)

        print("\n" + "="*60)
        print("✅ LISTENER AKTIF - Menunggu event dari kamera...")
        print("👋 Gerakkan tangan di depan kamera untuk trigger event!")
        print("="*60 + "\n")

        event_counter = 0

        # 5. LOOPING PENGAMBILAN DATA
        while True:
            try:
                response = pullpoint.PullMessages(Timeout='PT5S', MessageLimit=10)
                
                # Cek apakah ada NotificationMessage
                if hasattr(response, 'NotificationMessage'):
                    messages = response.NotificationMessage
                    
                    # Pastikan messages adalah list
                    if not isinstance(messages, list):
                        messages = [messages]
                    
                    for msg in messages:
                        event_counter += 1
                        
                        # DUMP LENGKAP SEMUA ATRIBUT
                        print("\n" + "="*60)
                        print(f"🔍 FULL DEBUG #{event_counter}")
                        print("="*60)
                        print(f"Type: {type(msg)}")
                        print(f"Dir: {[x for x in dir(msg) if not x.startswith('__')]}")
                        
                        # Cek setiap atribut
                        for attr in dir(msg):
                            if not attr.startswith('__'):
                                try:
                                    val = getattr(msg, attr)
                                    print(f"\n{attr}: {type(val)}")
                                    
                                    # Jika bukan method, print valuenya
                                    if not callable(val):
                                        if hasattr(val, '_value_1'):
                                            print(f"  -> _value_1: {val._value_1}")
                                            print(f"  -> _value_1 type: {type(val._value_1)}")
                                            
                                            # Jika _value_1 punya atribut lagi
                                            if hasattr(val._value_1, '__dict__'):
                                                print(f"  -> _value_1 dict: {val._value_1.__dict__}")
                                        else:
                                            print(f"  -> value: {val}")
                                except Exception as e:
                                    print(f"{attr}: ERROR - {e}")
                        
                        print("="*60)
                        
                        # Parse event ke JSON
                        event_json = parse_tapo_event(msg)
                        
                        # Tampilkan dengan format yang bagus
                        print("\n" + "─"*60)
                        print(f"📋 EVENT #{event_counter} - {datetime.now().strftime('%H:%M:%S')}")
                        print("─"*60)
                        
                        # Tampilkan ringkasan dengan warna
                        if event_json.get('is_people_detected'):
                            print("🚨 STATUS: PEOPLE DETECTED! 🚨")
                        else:
                            print(f"📌 Status: No People / Initialized")
                        
                        print(f"📂 Event Type: {event_json.get('event_type', 'Unknown')}")
                        print(f"⏰ Timestamp: {event_json.get('timestamp', 'N/A')}")
                        print(f"📡 Topic: {event_json.get('topic', 'N/A')}")
                        print(f"🔄 Operation: {event_json.get('property_operation', 'N/A')}")
                        
                        # Tampilkan Source
                        if event_json.get('source'):
                            print(f"\n📍 SOURCE:")
                            for key, val in event_json['source'].items():
                                print(f"   • {key}: {val}")
                        
                        # Tampilkan Data
                        if event_json.get('data'):
                            print(f"\n📊 DATA:")
                            for key, val in event_json['data'].items():
                                icon = "✅" if val == "true" else "❌"
                                print(f"   {icon} {key}: {val}")
                        
                        # Tampilkan JSON lengkap
                        print(f"\n📄 FULL JSON:")
                        json_str = json.dumps(event_json, indent=2, ensure_ascii=False)
                        print(json_str)
                        print("─"*60)
                        
                        # Optional: Simpan ke file
                        # filename = f'event_{event_counter}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                        # with open(filename, 'w', encoding='utf-8') as f:
                        #     json.dump(event_json, f, indent=2, ensure_ascii=False)
                        # print(f"💾 Saved to: {filename}")
                
                time.sleep(0.1)
                
            except Exception as e:
                error_msg = str(e).lower()
                if "timeout" not in error_msg and "no messages" not in error_msg:
                    logging.warning(f"⚠️  Error saat pulling messages: {e}")
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print("👋 Program dihentikan oleh user.")
        print(f"📊 Total events yang ditangkap: {event_counter}")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ [FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    get_tapo_proof_data()