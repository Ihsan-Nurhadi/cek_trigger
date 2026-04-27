import json
import time
import requests
import urllib3
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta

from .models import CameraSite, MotionNotification
from .hikvision_monitor import monitor_manager, register_sse_client, unregister_sse_client


# ─────────────────────────────────────────────────────────────
#  HELPER: Pecah rekaman menjadi segmen-segmen maksimal 10 menit
# ─────────────────────────────────────────────────────────────
import re as _re

SEGMENT_MINUTES = 10  # Panjang setiap segmen dalam menit

def _manipulate_uri_time(uri, seg_start, seg_end):
    """
    Ganti parameter starttime dan endtime pada playback URI (RTSP/ISAPI).
    Format yang didukung:
      - RTSP: rtsp://ip/.../tracks/101?starttime=20240101T080000Z&endtime=...
      - ISAPI download path: /ISAPI/ContentMgmt/download?playbackURI=...
    """
    # Format Hikvision RTSP: 20240101T080000Z (tanpa tanda hubung/titik dua)
    start_str = seg_start.strftime('%Y%m%dT%H%M%SZ')
    end_str   = seg_end.strftime('%Y%m%dT%H%M%SZ')

    # Ganti starttime=... dan endtime=... pada query string (format Hikvision RTSP)
    new_uri = _re.sub(r'starttime=[^&\s]+', f'starttime={start_str}', uri, flags=_re.IGNORECASE)
    new_uri = _re.sub(r'endtime=[^&\s]+',   f'endtime={end_str}',   new_uri, flags=_re.IGNORECASE)

    # Jika tidak ada parameter waktu di URI (URI tanpa query string), tambahkan
    if 'starttime=' not in new_uri.lower() and 'endtime=' not in new_uri.lower():
        sep = '&' if '?' in new_uri else '?'
        new_uri = f"{new_uri}{sep}starttime={start_str}&endtime={end_str}"

    return new_uri


def split_to_segments(raw_items, segment_minutes=SEGMENT_MINUTES):
    """
    Terima list raw_items = [{'uri': str, 'start': datetime, 'end': datetime}, ...].
    1. Urutkan berdasarkan start time.
    2. Merge interval yang overlap/bersebelahan (toleransi 1 detik).
    3. Pecah setiap interval menjadi segmen maksimal `segment_minutes` menit.
    4. Kembalikan list siap tampil: playback_uri, start_time, end_time, duration.
    Catatan: Karena semua file Hikvision memakai URI yang sama (hanya bedanya
    parameter waktu), kita pakai URI dari file pertama sebagai template.
    """
    if not raw_items:
        return []

    seg_min = timedelta(minutes=segment_minutes)

    # 1. Urutkan berdasarkan waktu mulai
    sorted_items = sorted(raw_items, key=lambda x: x['start'])

    # 2. Pecah menjadi segmen 10 menit tanpa menggabungkan file yang berbeda
    def fmt_local(dt):
        return (dt + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')

    segments = []
    for block in sorted_items:
        seg_start = block['start']
        block_end = block['end']
        uri_template = block['uri']
        file_start = block['start']

        while seg_start < block_end:
            seg_end = min(seg_start + seg_min, block_end)
            delta = seg_end - seg_start
            h, rem = divmod(int(delta.total_seconds()), 3600)
            m, s   = divmod(rem, 60)
            duration_str = f'{h:02d}:{m:02d}:{s:02d}'

            seg_uri = _manipulate_uri_time(uri_template, seg_start, seg_end)

            segments.append({
                'playback_uri': seg_uri,
                'start_time':   fmt_local(seg_start),
                'end_time':     fmt_local(seg_end),
                'duration':     duration_str,
                # Waktu UTC eksplisit untuk dikirim ke download endpoint
                'seg_start_utc': seg_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'seg_end_utc':   seg_end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'file_start_utc': file_start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            })
            seg_start = seg_end

    return segments


# ─────────────────────────────────────────────────────────────
#  EXISTING: search_hikvision helper
# ─────────────────────────────────────────────────────────────
def search_hikvision(ip, username, password, start_time, end_time, track_id="1"):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    payload = f"""<?xml version="1.0" encoding="utf-8"?>
    <CMSearchDescription>
        <searchID>{str(datetime.now().timestamp())}</searchID>
        <trackList>
            <trackID>{track_id}</trackID>
        </trackList>
        <timeSpanList>
            <timeSpan>
                <startTime>{start_time}</startTime>
                <endTime>{end_time}</endTime>
            </timeSpan>
        </timeSpanList>
        <maxResults>250</maxResults>
        <searchResultPostion>0</searchResultPostion>
    </CMSearchDescription>
    """

    headers = {'Content-Type': 'application/xml'}

    for scheme in ['https', 'http']:
        url = f"{scheme}://{ip}/ISAPI/ContentMgmt/search"
        try:
            response = requests.post(
                url, auth=HTTPDigestAuth(username, password),
                data=payload, headers=headers, timeout=10, verify=False
            )

            if response.status_code == 401:
                response = requests.post(
                    url, auth=(username, password),
                    data=payload, headers=headers, timeout=10, verify=False
                )

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                if 'ResponseStatus' in root.tag or root.find('.//statusCode') is not None:
                    error_msg = ET.tostring(root, encoding='unicode')
                    return {'success': False, 'error': 'Hikvision merespons dengan Error XML:', 'raw_xml': error_msg}

                raw_items = []
                for item in root.iter():
                    if 'searchMatchItem' in item.tag:
                        playback_uri = start_t = end_t = ""
                        for sub in item.iter():
                            if 'playbackURI' in sub.tag:
                                playback_uri = sub.text
                            elif 'startTime' in sub.tag:
                                start_t = sub.text
                            elif 'endTime' in sub.tag:
                                end_t = sub.text

                        if playback_uri and start_t and end_t:
                            try:
                                st = datetime.strptime(start_t, "%Y-%m-%dT%H:%M:%SZ")
                                et = datetime.strptime(end_t, "%Y-%m-%dT%H:%M:%SZ")
                                raw_items.append({'uri': playback_uri, 'start': st, 'end': et})
                            except:
                                pass

                results = split_to_segments(raw_items)
                raw_content = ET.tostring(root, encoding='unicode') if not results else ""
                return {'success': True, 'data': results, 'raw_xml': raw_content}

            return {'success': False, 'error': f"HTTP {response.status_code} — {response.text[:300]}"}

        except requests.exceptions.SSLError:
            continue
        except Exception as e:
            return {'success': False, 'error': str(e)}

    return {'success': False, 'error': 'Gagal terhubung via HTTPS maupun HTTP.'}


# ─────────────────────────────────────────────────────────────
#  EXISTING PAGES
# ─────────────────────────────────────────────────────────────
def index(request):
    return render(request, 'api_app/index.html')


@csrf_exempt
def logs_json(request):
    """Endpoint AJAX untuk mengambil rekaman dari Hikvision, return JSON."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    ip       = request.POST.get('ip', '')
    username = request.POST.get('username', '')
    password = request.POST.get('password', '')
    track_id = request.POST.get('track_id', '101')
    start_input = request.POST.get('start_time', '')
    end_input   = request.POST.get('end_time', '')

    if start_input and end_input:
        try:
            dt_start = datetime.strptime(start_input, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
            dt_end   = datetime.strptime(end_input,   '%Y-%m-%dT%H:%M') - timedelta(hours=7)
            start = dt_start.strftime('%Y-%m-%dT%H:%M:%SZ')
            end   = dt_end.strftime('%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            start = start_input + ':00Z'
            end   = end_input   + ':00Z'
    else:
        local_now  = datetime.now()
        local_start = local_now.replace(hour=0,  minute=0,  second=0)
        local_end   = local_now.replace(hour=23, minute=59, second=59)
        start = (local_start - timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end   = (local_end   - timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ')

    result = search_hikvision(ip, username, password, start, end, track_id)
    return JsonResponse(result)


def logs_history(request):
    context = {}

    if request.method == 'POST':
        ip       = request.POST.get('ip', '')
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        track_id = request.POST.get('track_id', '1')
        start_input = request.POST.get('start_time', '')
        end_input   = request.POST.get('end_time', '')
        do_search = True
    elif request.method == 'GET' and request.GET.get('autoload'):
        ip       = request.GET.get('ip', '')
        username = request.GET.get('username', '')
        password = request.GET.get('password', '')
        track_id = request.GET.get('track_id', '1')
        start_input = request.GET.get('start_time', '')
        end_input   = request.GET.get('end_time', '')
        do_search = True
    else:
        return render(request, 'api_app/logs_history.html', context)

    if do_search:
        if start_input and end_input:
            try:
                dt_start = datetime.strptime(start_input, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
                dt_end   = datetime.strptime(end_input,   '%Y-%m-%dT%H:%M') - timedelta(hours=7)
                start = dt_start.strftime('%Y-%m-%dT%H:%M:%SZ')
                end   = dt_end.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                start = start_input + ':00Z'
                end   = end_input   + ':00Z'
        else:
            local_now   = datetime.now()
            local_start = local_now.replace(hour=0,  minute=0,  second=0)
            local_end   = local_now.replace(hour=23, minute=59, second=59)
            start = (local_start - timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
            end   = (local_end   - timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ')

        result = search_hikvision(ip, username, password, start, end, track_id)
        context['ip']         = ip
        context['username']   = username
        context['password']   = password
        context['track_id']   = track_id
        context['start_time'] = start_input
        context['end_time']   = end_input
        context['result']     = result

    return render(request, 'api_app/logs_history.html', context)


def download_video(request):
    """
    Download segmen video dari Hikvision, dipotong tepat sesuai durasi segmen
    menggunakan FFmpeg. Hikvision ISAPI selalu mengirim seluruh file rekaman
    (bisa 1 jam+), jadi kita pipe hasilnya melalui FFmpeg untuk memotong
    hanya segmen yang diminta (max 10 menit).
    """
    if request.method != 'POST':
        return HttpResponse("Hanya menerima POST method.", status=400)

    ip               = request.POST.get('ip')
    username         = request.POST.get('username')
    password         = request.POST.get('password')
    playback_uri     = request.POST.get('playback_uri')
    seg_start_utc    = request.POST.get('seg_start_utc', '')
    seg_end_utc      = request.POST.get('seg_end_utc', '')
    file_start_utc   = request.POST.get('file_start_utc', '')
    start_time_label = request.POST.get('start_time', '').replace(' ', '_').replace(':', '-')

    import html, urllib3, subprocess, shutil
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ── Hitung durasi segmen (detik) untuk FFmpeg -t ──
    duration_secs = None
    offset_secs = 0
    if seg_start_utc and seg_end_utc:
        try:
            seg_start_dt  = datetime.strptime(seg_start_utc, '%Y-%m-%dT%H:%M:%SZ')
            seg_end_dt    = datetime.strptime(seg_end_utc,   '%Y-%m-%dT%H:%M:%SZ')
            duration_secs = int((seg_end_dt - seg_start_dt).total_seconds())
            playback_uri  = _manipulate_uri_time(playback_uri, seg_start_dt, seg_end_dt)
            print(f"DEBUG: duration_secs calculated = {duration_secs} from {seg_start_utc} to {seg_end_utc}")
            
            if file_start_utc:
                file_start_dt = datetime.strptime(file_start_utc, '%Y-%m-%dT%H:%M:%SZ')
                offset_secs = int((seg_start_dt - file_start_dt).total_seconds())
                if offset_secs < 0:
                    offset_secs = 0
                print(f"DEBUG: offset_secs calculated = {offset_secs} from file start {file_start_utc}")
        except Exception as e:
            print("DEBUG: Exception parsing duration or offset:", e)
    else:
        print("DEBUG: missing seg_start_utc or seg_end_utc", seg_start_utc, seg_end_utc)

    ffmpeg_bin = shutil.which('ffmpeg')
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            print("Successfully found ffmpeg via imageio_ffmpeg:", ffmpeg_bin)
        except Exception as e:
            print("Failed to load imageio_ffmpeg:", repr(e))
            import traceback
            traceback.print_exc()
            ffmpeg_bin = None
            
        import sys, os
        # Absolute fallback known good path in this environment
        fallback_path = r"C:\Users\nasch\AppData\Local\Programs\Python\Python313\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
        if not ffmpeg_bin and os.path.exists(fallback_path):
            ffmpeg_bin = fallback_path
            print("Using absolute fallback ffmpeg path:", ffmpeg_bin)
    else:
        print("Successfully found ffmpeg via shutil:", ffmpeg_bin)

    # ── Payload ISAPI download ──
    xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<downloadRequest>
<playbackURI>{html.escape(playback_uri)}</playbackURI>
</downloadRequest>"""
    dl_headers = {'Content-Type': 'application/xml'}
    params     = {'playbackURI': playback_uri}

    # ── Coba koneksi ke Hikvision ──
    attempts = []
    for scheme in ['https', 'http']:
        base_url = f"{scheme}://{ip}/ISAPI/ContentMgmt/download"
        attempts.append(lambda u=base_url: requests.post(
            u, auth=HTTPDigestAuth(username, password),
            data=xml_payload, headers=dl_headers, stream=True, timeout=(15, None), verify=False))
        attempts.append(lambda u=base_url: requests.get(
            u, params=params, auth=HTTPDigestAuth(username, password),
            stream=True, timeout=(15, None), verify=False))
        attempts.append(lambda u=base_url: requests.post(
            u, auth=(username, password),
            data=xml_payload, headers=dl_headers, stream=True, timeout=(15, None), verify=False))

    try:
        r = None
        exception_msgs = []
        for i, attempt in enumerate(attempts):
            try:
                r = attempt()
                if r.status_code == 200:
                    break
                exception_msgs.append(f"Metode {i+1}: HTTP {r.status_code}")
            except Exception as ex:
                exception_msgs.append(f"Metode {i+1} error: {str(ex)}")

        if not (r and r.status_code == 200):
            final_status = r.status_code if r else 'Timeout/Connection-Error'
            debug_info   = "\n".join(exception_msgs)
            final_text   = r.text[:500] if r else f'Tidak ada respon.\n\nDetail:\n{debug_info}'
            return HttpResponse(
                f"<div style='font-family:sans-serif;padding:20px'>"
                f"<h2>Gagal Download</h2>"
                f"<p><strong style='color:red'>Status Akhir: HTTP {final_status}</strong></p>"
                f"<pre style='background:#f4f4f4;padding:12px;border-radius:6px;font-size:12px'>"
                f"{final_text}\n\n--- Detail ---\n{debug_info}</pre></div>")

        filename = f"Rekaman_Hikvision_{start_time_label}.mp4"

        # ── Jika FFmpeg tersedia DAN kita tahu durasi → potong tepat ──
        print(f"DEBUG: evaluating condition -> ffmpeg_bin: {bool(ffmpeg_bin)}, duration_secs: {duration_secs}")
        if ffmpeg_bin and duration_secs and duration_secs > 0:
            print("DEBUG: Using FFmpeg to split video", ffmpeg_bin, duration_secs, "offset:", offset_secs)
            # ffmpeg: baca dari stdin (pipe), lewati offset, potong -t <duration>, output ke stdout
            ffmpeg_cmd = [
                ffmpeg_bin,
                '-y',
                '-i', 'pipe:0',          # input dari stdin
            ]
            
            # Use output seeking (-ss after -i) because pipe:0 is not seekable
            if offset_secs > 0:
                ffmpeg_cmd.extend(['-ss', str(offset_secs)])
                
            ffmpeg_cmd.extend([
                '-t', str(duration_secs), # potong sesuai durasi segmen
                '-c', 'copy',            # tidak re-encode (cepat)
                '-movflags', 'frag_keyframe+empty_moov+faststart',
                '-f', 'mp4',
                'pipe:1',                # output ke stdout
            ])

            proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            def feed_and_read(hikvision_response, ffmpeg_proc):
                """Generator: umpankan data kamera ke FFmpeg stdin, baca stdout."""
                import threading

                def _writer():
                    try:
                        for chunk in hikvision_response.iter_content(chunk_size=65536):
                            if chunk:
                                ffmpeg_proc.stdin.write(chunk)
                    except Exception:
                        pass
                    finally:
                        try:
                            ffmpeg_proc.stdin.close()
                        except Exception:
                            pass

                writer_thread = threading.Thread(target=_writer, daemon=True)
                writer_thread.start()

                while True:
                    data = ffmpeg_proc.stdout.read(65536)
                    if not data:
                        break
                    yield data

                writer_thread.join(timeout=5)
                ffmpeg_proc.wait()

            response = StreamingHttpResponse(
                feed_and_read(r, proc),
                content_type='video/mp4'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        else:
            # Fallback: tidak ada FFmpeg → kirim file lengkap dari kamera
            # (tampilkan peringatan di nama file)
            if not ffmpeg_bin:
                filename = f"FULL_Rekaman_{start_time_label}.mp4"
            response = StreamingHttpResponse(r.iter_content(chunk_size=8192), content_type='video/mp4')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    except Exception as e:
        return HttpResponse(f"<h2>Error Server</h2><p>{str(e)}</p>", status=500)


def stream_camera(request):
    ip = "192.168.68.101"
    https_port = 443
    http_port = 80
    user = "Nayakaws"
    password = "nayakaprtm2"
    channel = request.GET.get('channel', '101')

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    url = f"https://{ip}:{https_port}/ISAPI/Streaming/channels/{channel}/httppreview"

    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, password), stream=True, timeout=(5, None), verify=False)
        if r.status_code == 401:
            r = requests.get(url, auth=(user, password), stream=True, timeout=(5, None), verify=False)

        if r.status_code == 200:
            content_type = r.headers.get('Content-Type', 'multipart/x-mixed-replace; boundary=--myboundary')
            return StreamingHttpResponse(r.iter_content(chunk_size=4096), content_type=content_type)

        snapshot_url = f"http://{ip}:{http_port}/ISAPI/Streaming/channels/{channel}/picture"
        r2 = requests.get(snapshot_url, auth=HTTPDigestAuth(user, password), timeout=(5, 10), verify=False)
        if r2.status_code == 401:
            r2 = requests.get(snapshot_url, auth=(user, password), timeout=(5, 10), verify=False)
        if r2.status_code == 200:
            return HttpResponse(r2.content, content_type=r2.headers.get('Content-Type', 'image/jpeg'))

        return HttpResponse(
            f"<pre>Gagal stream kamera\nURL: {url}\nStatus: {r.status_code}</pre>",
            status=r.status_code)

    except requests.exceptions.ConnectTimeout:
        return HttpResponse(f"<pre>Timeout koneksi ke {ip}:{https_port}</pre>", status=504)
    except Exception as e:
        return HttpResponse(f"<pre>Error: {str(e)}</pre>", status=500)


# ─────────────────────────────────────────────────────────────
#  NEW: SITE MANAGEMENT  /sites/
# ─────────────────────────────────────────────────────────────
def sites_list(request):
    """GET /sites/ — return list semua site sebagai JSON."""
    sites = list(CameraSite.objects.values(
        'id', 'name', 'ip', 'port', 'username', 'password',
        'track_id', 'lat', 'lng', 'is_active'
    ))
    return JsonResponse({'sites': sites})


@csrf_exempt
def sites_add(request):
    """POST /sites/add/ — tambah site baru (validasi maks 2)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    try:
        site = CameraSite(
            name=data.get('name', '').strip(),
            ip=data.get('ip', '').strip(),
            port=int(data.get('port', 80)),
            username=data.get('username', '').strip(),
            password=data.get('password', '').strip(),
            track_id=data.get('track_id', '1').strip(),
            lat=float(data.get('lat', 0)),
            lng=float(data.get('lng', 0)),
            is_active=True,
        )
        site.save()  # ValidationError jika sudah 2 site

        # Start monitor untuk site baru
        monitor_manager.start_site(site)

        return JsonResponse({
            'success': True,
            'site': {
                'id': site.id, 'name': site.name, 'ip': site.ip,
                'port': site.port, 'username': site.username, 'password': site.password,
                'track_id': site.track_id, 'lat': site.lat, 'lng': site.lng,
                'is_active': site.is_active,
            }
        })
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e.message)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def sites_delete(request, site_id):
    """POST /sites/<id>/delete/ — hapus site + stop monitor."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        site = CameraSite.objects.get(pk=site_id)
        monitor_manager.stop_site(site_id)
        site.delete()
        return JsonResponse({'success': True})
    except CameraSite.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Site tidak ditemukan.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def sites_toggle(request, site_id):
    """POST /sites/<id>/toggle/ — aktif/nonaktif monitor."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        site = CameraSite.objects.get(pk=site_id)
        site.is_active = not site.is_active
        site.save()

        if site.is_active:
            monitor_manager.start_site(site)
        else:
            monitor_manager.stop_site(site_id)

        return JsonResponse({'success': True, 'is_active': site.is_active})
    except CameraSite.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Site tidak ditemukan.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def sites_update(request, site_id):
    """POST /sites/<id>/update/ — update data site (termasuk lat/lng)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    try:
        site = CameraSite.objects.get(pk=site_id)

        # Update field jika dikirimkan
        if 'name' in data and data['name'].strip():
            site.name = data['name'].strip()
        if 'ip' in data and data['ip'].strip():
            site.ip = data['ip'].strip()
        if 'port' in data:
            site.port = int(data['port'])
        if 'username' in data and data['username'].strip():
            site.username = data['username'].strip()
        if 'password' in data and data['password'].strip():
            site.password = data['password'].strip()
        if 'track_id' in data:
            site.track_id = data['track_id'].strip()
        if 'lat' in data:
            site.lat = float(data['lat'])
        if 'lng' in data:
            site.lng = float(data['lng'])

        site.save()

        # Restart monitor jika site aktif supaya pakai kredensial baru
        if site.is_active:
            monitor_manager.stop_site(site_id)
            monitor_manager.start_site(site)

        return JsonResponse({
            'success': True,
            'site': {
                'id': site.id, 'name': site.name, 'ip': site.ip,
                'port': site.port, 'username': site.username, 'password': site.password,
                'track_id': site.track_id, 'lat': site.lat, 'lng': site.lng,
                'is_active': site.is_active,
            }
        })
    except CameraSite.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Site tidak ditemukan.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────
#  NEW: NOTIFICATIONS  /notifications/
# ─────────────────────────────────────────────────────────────
def notifications_list(request):
    """GET /notifications/ — return 20 notifikasi terbaru."""
    notifs = MotionNotification.objects.exclude(event_type='motion_stop').select_related('site').order_by('-timestamp')[:20]
    data = []
    for n in notifs:
        data.append({
            'id'        : n.id,
            'site_name' : n.site_name,
            'channel'   : n.channel,
            'event_type': n.event_type,
            'timestamp' : (n.timestamp + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S WIB'),
            'is_read'   : n.is_read,
        })
    unread_count = MotionNotification.objects.filter(is_read=False).exclude(event_type='motion_stop').count()
    return JsonResponse({'notifications': data, 'unread_count': unread_count})


@csrf_exempt
def notifications_mark_read(request):
    """POST /notifications/mark-read/ — tandai semua / 1 notifikasi dibaca."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}

    notif_id = body.get('id')
    if notif_id:
        MotionNotification.objects.filter(pk=notif_id).update(is_read=True)
    else:
        MotionNotification.objects.filter(is_read=False).update(is_read=True)

    unread_count = MotionNotification.objects.filter(is_read=False).exclude(event_type='motion_stop').count()
    return JsonResponse({'success': True, 'unread_count': unread_count})


def notifications_sse(request):
    """
    GET /notifications/sse/
    Server-Sent Events endpoint — push real-time ke browser saat ada motion event baru.
    """
    q = register_sse_client()

    def event_stream():
        # Kirim heartbeat pertama agar browser tahu koneksi aktif
        yield "data: {\"type\": \"connected\"}\n\n"
        try:
            while True:
                try:
                    # Tunggu event baru (timeout 25 detik untuk heartbeat)
                    msg = q.get(timeout=25)
                    yield msg
                except Exception:
                    # Heartbeat jika tidak ada event
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            unregister_sse_client(q)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response

# ─────────────────────────────────────────────────────────────
#  NEW: MQTT DEVICE CONTROL
# ─────────────────────────────────────────────────────────────
def mqtt_status(request):
    """GET /api/mqtt/status/ — return latest mqtt data."""
    try:
        from .mqtt_service import LATEST_MQTT_DATA
        return JsonResponse({'success': True, 'data': LATEST_MQTT_DATA})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def mqtt_command(request):
    """POST /api/mqtt/command/ — send command to MQTT."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        body = json.loads(request.body)
    except Exception:
        body = request.POST

    device_id = body.get('device_id', 'NMS_002')
    cmd = body.get('cmd')
    state = body.get('state')

    if cmd is None or state is None:
        return JsonResponse({'success': False, 'error': 'cmd dan state diperlukan.'}, status=400)

    try:
        state = int(state)
    except ValueError:
        pass

    try:
        from .mqtt_service import publish_command
        success = publish_command(device_id, cmd, state)
        if success:
            return JsonResponse({'success': True, 'message': f"Sent {cmd}:{state} to {device_id}"})
        else:
            return JsonResponse({'success': False, 'error': 'MQTT not connected / failed to publish'}, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def mqtt_siren(request):
    """POST /api/mqtt/siren/ — publish siren command ke ny/command/tower/nms.
    Body JSON: { "device": "site_1", "playList": 1, "volume": 33 }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Hanya menerima POST.'}, status=400)

    try:
        body = json.loads(request.body)
    except Exception:
        body = request.POST

    device   = body.get('device', 'site_1')
    play_list = body.get('playList')
    volume   = body.get('volume', 50)

    if play_list is None:
        return JsonResponse({'success': False, 'error': 'playList diperlukan.'}, status=400)

    try:
        from .mqtt_service import publish_siren
        success = publish_siren(device, play_list, volume)
        if success:
            return JsonResponse({
                'success': True,
                'message': f"Siren {play_list} triggered on {device} (vol={volume})"
            })
        else:
            return JsonResponse({'success': False, 'error': 'MQTT not connected / failed to publish'}, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def history_snapshots(request):
    """GET /api/history/snapshots/ — return history split (camera & pir)."""
    try:
        from django.conf import settings
        from .models import SnapshotHistory
        site_id = request.GET.get('site_id')
        start_time = request.GET.get('start_time')
        end_time = request.GET.get('end_time')

        qs = SnapshotHistory.objects.all().select_related('site')
        if site_id:
            qs = qs.filter(site_id=site_id)
        
        if start_time and end_time:
            try:
                dt_start = datetime.strptime(start_time, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
                dt_end   = datetime.strptime(end_time,   '%Y-%m-%dT%H:%M') - timedelta(hours=7)
                qs = qs.filter(timestamp__gte=dt_start, timestamp__lte=dt_end)
            except ValueError:
                pass

        camera_qs = qs.filter(trigger_source='CAMERA')
        pir_qs = qs.exclude(trigger_source='CAMERA')
        
        def format_qs(queryset):
            res = []
            for item in queryset:
                res.append({
                    'id': item.id,
                    'site_name': item.site.name,
                    'trigger_source': item.trigger_source,
                    'timestamp': (item.timestamp + timedelta(hours=7)).strftime('%A, %d %B %Y %H:%M:%S'),
                    'image_url': f"/{settings.MEDIA_URL.strip('/')}/{item.image_path}",
                })
            return res

        return JsonResponse({
            'success': True,
            'camera_history': format_qs(camera_qs[:100]),
            'pir_history': format_qs(pir_qs[:100]),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def camera_sdcard_status(request):
    """GET /api/camera/sdcard/ — return SD Card status via ISAPI."""
    ip = request.POST.get('ip') or request.GET.get('ip')
    username = request.POST.get('username') or request.GET.get('username')
    password = request.POST.get('password') or request.GET.get('password')

    if not all([ip, username, password]):
        return JsonResponse({'success': False, 'error': 'Missing credentials'}, status=400)
        
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        url = f"http://{ip}/ISAPI/ContentMgmt/Storage"
        r = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=5, verify=False)
        if r.status_code == 401:
            r = requests.get(url, auth=(username, password), timeout=5, verify=False)
        
        if r.status_code == 200:
            import re
            # Strip XML namespaces for easier parsing
            xml_content = re.sub(r'\sxmlns="[^"]+"', '', r.text)
            root = ET.fromstring(xml_content)
            
            hdds = []
            for hdd in root.findall('.//hdd'):
                hdd_data = {
                    'id': getattr(hdd.find('id'), 'text', ''),
                    'name': getattr(hdd.find('hddName'), 'text', ''),
                    'type': getattr(hdd.find('hddType'), 'text', ''),
                    'status': getattr(hdd.find('status'), 'text', ''),
                    'capacity': getattr(hdd.find('capacity'), 'text', '0'),
                    'freeSpace': getattr(hdd.find('freeSpace'), 'text', '0'),
                    'property': getattr(hdd.find('property'), 'text', ''),
                }
                try:
                    hdd_data['capacity'] = int(hdd_data['capacity'])
                    hdd_data['freeSpace'] = int(hdd_data['freeSpace'])
                except ValueError:
                    pass
                hdds.append(hdd_data)

            return JsonResponse({'success': True, 'hdds': hdds})
        else:
            return JsonResponse({'success': False, 'error': f'HTTP {r.status_code}'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
