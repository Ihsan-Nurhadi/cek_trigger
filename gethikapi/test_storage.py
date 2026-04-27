import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

ip = "192.168.68.101"
user = "Nayakaws"
password = "nayakaprtm2"

url = f"http://{ip}/ISAPI/ContentMgmt/Storage"
try:
    r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=5, verify=False)
    if r.status_code == 401:
        r = requests.get(url, auth=(user, password), timeout=5, verify=False)
    print("Status:", r.status_code)
    print("Content:\n", r.text)
except Exception as e:
    print("Error:", e)
