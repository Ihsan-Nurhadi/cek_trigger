import requests
import urllib3
from requests.auth import HTTPDigestAuth

# Nonaktifkan SSL warning karena kamera pakai self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ip = "192.168.68.101"
user = "Nayakaws"
pwd = "nayakaprtm2"

def check(url):
    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, pwd), timeout=5, verify=False)
        print(f"{url} -> {r.status_code}")
    except Exception as e:
        print(f"{url} -> Error: {e}")

# Test HTTPS port 443
print("=== HTTPS (port 443) ===")
check(f"https://{ip}/ISAPI/System/deviceInfo")
check(f"https://{ip}/ISAPI/Streaming/channels")
check(f"https://{ip}/ISAPI/Streaming/channels/101/httppreview")
check(f"https://{ip}/ISAPI/Streaming/channels/101/picture")

# Test HTTP port 80 (fallback)
print("\n=== HTTP (port 80) ===")
check(f"http://{ip}/ISAPI/System/deviceInfo")
check(f"http://{ip}/ISAPI/Streaming/channels/101/picture")
