import os
import time
import requests
import urllib3
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from .models import SnapshotHistory, CameraSite

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def capture_snapshot_from_camera(site_id, trigger_source):
    """
    trigger_source: "CAMERA", "PIR_1", "PIR_2", "PIR_3", "PIR_4"
    """
    try:
        site = CameraSite.objects.get(id=site_id)
        
        # Debounce: Mencegah spam. Misal max 1 snapshot per trigger_source tiap 10 detik.
        recent = SnapshotHistory.objects.filter(
            site=site, 
            trigger_source=trigger_source,
            timestamp__gte=timezone.now() - timedelta(seconds=10)
        ).first()
        
        if recent:
            print(f"[Snapshot] Skipped (debounce) for {trigger_source} at site {site.name}")
            return None

        # Build ISAPI request for picture
        url = f"http://{site.ip}:{site.port}/ISAPI/Streaming/channels/{site.track_id}/picture"
        
        # Coba auth
        r = requests.get(url, auth=HTTPDigestAuth(site.username, site.password), timeout=(5, 10), verify=False)
        if r.status_code == 401:
            r = requests.get(url, auth=(site.username, site.password), timeout=(5, 10), verify=False)
            
        if r.status_code == 200:
            # Pastikan folder media/snapshots/ ada
            media_dir = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
            snapshots_dir = os.path.join(media_dir, 'snapshots')
            os.makedirs(snapshots_dir, exist_ok=True)
            
            # Buat nama file unik
            # format: YYYYMMDD_HHMMSS
            time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"snap_site{site.id}_{trigger_source}_{time_str}.jpg"
            file_path = os.path.join(snapshots_dir, filename)
            
            with open(file_path, 'wb') as f:
                f.write(r.content)
            
            # Simpan path-nya yang bisa diakses via web (relative media url)
            # Kita simpan absolute path file saja, nanti disajikan via endpoint/url dengan string replace atau custom logic,
            # lebih baik relative URL dari media root agar bisa di-serve oleh Django.
            relative_url = f"snapshots/{filename}"
            
            sh = SnapshotHistory.objects.create(
                site=site,
                trigger_source=trigger_source,
                image_path=relative_url
            )
            print(f"[Snapshot] Berhasil difoto {trigger_source} -> {filename}")
            return sh
        else:
            print(f"[Snapshot] Failed HTTP {r.status_code} from {site.ip}")
            return None
            
    except CameraSite.DoesNotExist:
        print(f"[Snapshot] Gagal: site ID {site_id} tidak ditemukan.")
        return None
    except Exception as e:
        print(f"[Snapshot] Error taking picture: {e}")
        return None
