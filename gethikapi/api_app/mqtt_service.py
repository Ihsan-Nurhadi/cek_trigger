import json
import logging
import threading
from datetime import datetime
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

MQTT_SERVER = "202.155.90.125"
MQTT_PORT = 1883
MQTT_USER = "sensor"
MQTT_PASSWORD = "Naya@client123"
MQTT_TOPIC_DATA = "ny/data/tower/nms"
MQTT_TOPIC_COMMAND = "ny/command/tower/nms"
MQTT_TOPIC_PIR = "ny/data/tower/pir"

LATEST_MQTT_DATA = {
    "NMS_002": {
        "door": "CLOSE",
        "pln": "OFF",
        "last_updated": "--.--.--"
    }
}

client = None

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC_DATA)
        client.subscribe(MQTT_TOPIC_PIR)
    else:
        print(f"[MQTT] Failed to connect to MQTT broker, return code {rc}")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode('utf-8'))
        
        if topic == MQTT_TOPIC_PIR:
            # Expected payload: {"device":"site_1","pir_id":4,"pin":34,"motion":0,"status":"NO_MOTION"}
            pir_id = str(payload.get("pir_id"))
            
            # Map default to NMS_002 since frontend uses it as default device_id
            if "NMS_002" not in LATEST_MQTT_DATA:
                LATEST_MQTT_DATA["NMS_002"] = {}
            if "pir" not in LATEST_MQTT_DATA["NMS_002"]:
                LATEST_MQTT_DATA["NMS_002"]["pir"] = {}
                
            motion = payload.get("motion", 0)
            status = payload.get("status", "NO_MOTION")
            LATEST_MQTT_DATA["NMS_002"]["pir"][pir_id] = {
                "motion": motion,
                "status": status
            }
            
            if motion == 1 or status == "MOTION":
                # Trigger snapshot
                try:
                    from .models import CameraSite
                    from .utils_hikvision import capture_snapshot_from_camera
                    # Use first active site
                    site = CameraSite.objects.filter(is_active=True).first()
                    if site:
                        trigger_source = f"PIR_{pir_id}"
                        capture_snapshot_from_camera(site.id, trigger_source)
                except Exception as e:
                    print(f"[MQTT] Error capturing PIR snapshot: {e}")
            
            now = datetime.now()
            LATEST_MQTT_DATA["NMS_002"]["last_updated"] = now.strftime("%H.%M.%S")
            
        elif topic == MQTT_TOPIC_DATA:
            device_id = payload.get("device_id")
            
            if device_id and "data" in payload:
                if device_id not in LATEST_MQTT_DATA:
                    LATEST_MQTT_DATA[device_id] = {}
                    
                data = payload["data"]
                if "door" in data:
                    LATEST_MQTT_DATA[device_id]["door"] = data["door"].upper()
                if "pln" in data:
                    LATEST_MQTT_DATA[device_id]["pln"] = data["pln"].upper()
                    
                now = datetime.now()
                LATEST_MQTT_DATA[device_id]["last_updated"] = now.strftime("%H.%M.%S")
                
                if "ts" in payload:
                    LATEST_MQTT_DATA[device_id]["ts"] = payload["ts"]
                
    except Exception as e:
        print(f"[MQTT] Error processing MQTT message: {e}")

def get_status(device_id="NMS_002"):
    return LATEST_MQTT_DATA.get(device_id, {})

def publish_command(device_id, cmd, state):
    global client
    if client and client.is_connected():
        payload = {
            "device_id": device_id,
            "cmd": cmd,
            "state": state
        }
        client.publish(MQTT_TOPIC_COMMAND, json.dumps(payload))
        return True
    return False

def publish_siren(device, play_list, volume):
    """Publish siren command ke topic ny/command/tower/nms.
    Payload: {"device": "site_1", "playList": 1, "volume": 33}
    """
    global client
    if client and client.is_connected():
        payload = {
            "device": device,
            "playList": int(play_list),
            "volume": int(volume)
        }
        client.publish(MQTT_TOPIC_COMMAND, json.dumps(payload))
        print(f"[MQTT] Siren published: {json.dumps(payload)}")
        return True
    print("[MQTT] publish_siren failed: not connected")
    return False

def _run_mqtt():
    global client
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_SERVER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"[MQTT] Connection error: {e}")

def start_mqtt():
    t = threading.Thread(target=_run_mqtt, daemon=True, name='mqtt-service')
    t.start()
