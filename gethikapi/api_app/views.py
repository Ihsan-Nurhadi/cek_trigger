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
        <maxResults>40</maxResults>
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

                results = []
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

                        def fmt(t):
                            try:
                                dt = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
                                return (dt + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                return t.replace('T', ' ').replace('Z', '')

                        if playback_uri:
                            results.append({
                                'playback_uri': playback_uri,
                                'start_time':   fmt(start_t),
                                'end_time':     fmt(end_t)
                            })

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
    if request.method == 'POST':
        ip           = request.POST.get('ip')
        username     = request.POST.get('username')
        password     = request.POST.get('password')
        playback_uri = request.POST.get('playback_uri')
        start_time   = request.POST.get('start_time', '').replace(' ', '_').replace(':', '-')

        import html, urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<downloadRequest>
<playbackURI>{html.escape(playback_uri)}</playbackURI>
</downloadRequest>"""

        headers = {'Content-Type': 'application/xml'}
        params  = {'playbackURI': playback_uri}

        attempts = []
        for scheme in ['https', 'http']:
            base_url = f"{scheme}://{ip}/ISAPI/ContentMgmt/download"
            attempts.append(lambda u=base_url: requests.post(
                u, auth=HTTPDigestAuth(username, password),
                data=xml_payload, headers=headers, stream=True, timeout=60, verify=False))
            attempts.append(lambda u=base_url: requests.get(
                u, params=params, auth=HTTPDigestAuth(username, password),
                stream=True, timeout=60, verify=False))
            attempts.append(lambda u=base_url: requests.post(
                u, auth=(username, password),
                data=xml_payload, headers=headers, stream=True, timeout=60, verify=False))
            attempts.append(lambda u=base_url: requests.get(
                u, params=params, auth=(username, password),
                stream=True, timeout=60, verify=False))

        try:
            r = None
            exception_msgs = []
            for i, attempt in enumerate(attempts):
                try:
                    r = attempt()
                    if r.status_code == 200:
                        break
                    else:
                        exception_msgs.append(f"Metode {i+1}: HTTP {r.status_code}")
                except Exception as ex:
                    exception_msgs.append(f"Metode {i+1} error: {str(ex)}")
                    continue

            if r and r.status_code == 200:
                response = StreamingHttpResponse(r.iter_content(chunk_size=8192), content_type='video/mp4')
                filename = f"Rekaman_Hikvision_{start_time}.mp4"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            else:
                final_status = r.status_code if r else 'Timeout/Connection-Error'
                debug_info   = "\n".join(exception_msgs)
                final_text   = r.text[:1000] if r else f'Tidak ada respon.\n\nDetail:\n{debug_info}'
                return HttpResponse(
                    f"<div style='font-family:sans-serif;padding:20px'>"
                    f"<h2>Gagal Download</h2>"
                    f"<p><strong style='color:red'>Status Akhir: HTTP {final_status}</strong></p>"
                    f"<pre style='background:#f4f4f4;padding:12px;border-radius:6px;font-size:12px'>{final_text}\n\n--- Detail ---\n{debug_info}</pre>"
                    f"</div>")
        except Exception as e:
            return HttpResponse(f"<h2>Error Server</h2><p>{str(e)}</p>")

    return HttpResponse("Hanya menerima POST method.", status=400)


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


# ─────────────────────────────────────────────────────────────
#  NEW: NOTIFICATIONS  /notifications/
# ─────────────────────────────────────────────────────────────
def notifications_list(request):
    """GET /notifications/ — return 20 notifikasi terbaru."""
    notifs = MotionNotification.objects.select_related('site').order_by('-timestamp')[:20]
    data = []
    for n in notifs:
        data.append({
            'id'        : n.id,
            'site_name' : n.site_name,
            'channel'   : n.channel,
            'event_type': n.event_type,
            'timestamp' : n.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_read'   : n.is_read,
        })
    unread_count = MotionNotification.objects.filter(is_read=False).count()
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

    unread_count = MotionNotification.objects.filter(is_read=False).count()
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
