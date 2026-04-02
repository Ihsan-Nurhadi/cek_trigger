import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse
from datetime import datetime, timedelta

def search_hikvision(ip, username, password, start_time, end_time, track_id="101"):
    url = f"http://{ip}/ISAPI/ContentMgmt/search"
    
    # Hikvision requires an XML payload for the search
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
    
    headers = {
        'Content-Type': 'application/xml',
    }
    
    try:
        response = requests.post(url, auth=HTTPDigestAuth(username, password), data=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            
            # Check if it returned a ResponseStatus error instead of a search result
            if 'ResponseStatus' in root.tag or root.find('.//statusCode') is not None:
                error_msg = ET.tostring(root, encoding='unicode')
                return {'success': False, 'error': "Hikvision merespons dengan Error XML:", 'raw_xml': error_msg}
                
            results = []
            
            # Using simple iteration to ignore namespaces
            for item in root.iter():
                if 'searchMatchItem' in item.tag:
                    playback_uri = ""
                    start_t = ""
                    end_t = ""
                    
                    # Cari secara rekursif di dalam item ini (tidak peduli seberapa dalam tag itu disarangkan)
                    for sub in item.iter():
                        if 'playbackURI' in sub.tag:
                            playback_uri = sub.text
                        elif 'startTime' in sub.tag:
                            start_t = sub.text
                        elif 'endTime' in sub.tag:
                            end_t = sub.text
                    
                    # Format waktu dari UTC kembali ke WIB lokal (+7) dan hilangkan T & Z
                    def format_hik_time(t_str):
                        try:
                            # Parse format Hikvision 2026-04-02T02:27:57Z (UTC)
                            dt = datetime.strptime(t_str, "%Y-%m-%dT%H:%M:%SZ")
                            # Tambah 7 Jam untuk Waktu Indonesia Barat
                            dt_local = dt + timedelta(hours=7)
                            # Format ulang jadi rapi "2026-04-02 09:27:57"
                            return dt_local.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            # Jika formatnya tiba-tiba beda, fallback dengan hilangkan huruf saja
                            return t_str.replace('T', ' ').replace('Z', '')
                    
                    if playback_uri:
                        results.append({
                            'playback_uri': playback_uri,
                            'start_time': format_hik_time(start_t),
                            'end_time': format_hik_time(end_t)
                        })
            
            # If no results but search was successful, attach raw XML to help debug
            raw_content = ET.tostring(root, encoding='unicode') if not results else ""
            return {'success': True, 'data': results, 'raw_xml': raw_content}
            
        elif response.status_code == 401:
            # Fallback to Basic Auth just in case
            response = requests.post(url, auth=(username, password), data=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                # Recursive call is scary, let's just return error for now indicating auth issue
                return {'success': False, 'error': f"HTTP 401 Unauthorized - Kemungkinan Username/Password salah, atau kamera butuh Basic Auth."}
            return {'success': False, 'error': f"HTTP {response.status_code} - {response.text}"}
        else:
            return {'success': False, 'error': f"HTTP {response.status_code} - {response.text}"}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def index(request):
    context = {}
    if request.method == 'POST':
        ip = request.POST.get('ip')
        username = request.POST.get('username')
        password = request.POST.get('password')
        track_id = request.POST.get('track_id', '101')
        start_input = request.POST.get('start_time')
        end_input = request.POST.get('end_time')
        
        if start_input and end_input:
            # Input user asalnya dari local (e.g. 2026-04-02T09:00). Ubah ke string lalu kurangi 7 jam menjadi UTC.
            try:
                dt_start = datetime.strptime(start_input, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
                dt_end = datetime.strptime(end_input, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
                start = dt_start.strftime('%Y-%m-%dT%H:%M:%SZ')
                end = dt_end.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                # Fallback
                start = start_input + ':00Z'
                end = end_input + ':00Z'
        else:
            # Default search span is today (Local time converted to UTC)
            local_now = datetime.now()
            local_start = local_now.replace(hour=0, minute=0, second=0)
            local_end = local_now.replace(hour=23, minute=59, second=59)
            
            start = (local_start - timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
            end = (local_end - timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        result = search_hikvision(ip, username, password, start, end, track_id)
        
        context['ip'] = ip
        context['username'] = username
        context['password'] = password
        context['track_id'] = track_id
        context['start_time'] = start_input
        context['end_time'] = end_input
        context['result'] = result
        
    return render(request, 'api_app/index.html', context)
    
def download_video(request):
    if request.method == 'POST':
        ip = request.POST.get('ip')
        username = request.POST.get('username')
        password = request.POST.get('password')
        playback_uri = request.POST.get('playback_uri')
        start_time = request.POST.get('start_time', '').replace(' ', '_').replace(':', '-')
        
        print(f"DEBUG DOWNLOAD: IP={ip}, USER={username}, PASS={password}, URI={playback_uri}")
        
        url = f"http://{ip}/ISAPI/ContentMgmt/download"
        
        import html
        xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<downloadRequest>
<playbackURI>{html.escape(playback_uri)}</playbackURI>
</downloadRequest>"""
        
        try:
            headers = {'Content-Type': 'application/xml'}
            params = {'playbackURI': playback_uri}
            
            # Kita akan mencoba 4 kombinasi sampai salah satu berhasil menghasilkan 200 OK
            attempts = [
                # 1. POST dengan Digest Auth (Paling standar untuk NVR terbaru)
                lambda: requests.post(url, auth=HTTPDigestAuth(username, password), data=xml_payload, headers=headers, stream=True, timeout=60),
                
                # 2. GET dengan Digest Auth (Standar URL Query)
                lambda: requests.get(url, params=params, auth=HTTPDigestAuth(username, password), stream=True, timeout=60),
                
                # 3. POST dengan Basic Auth
                lambda: requests.post(url, auth=(username, password), data=xml_payload, headers=headers, stream=True, timeout=60),
                
                # 4. GET dengan Basic Auth
                lambda: requests.get(url, params=params, auth=(username, password), stream=True, timeout=60)
            ]
            
            r = None
            exception_msgs = []
            for i, attempt in enumerate(attempts):
                try:
                    r = attempt()
                    if r.status_code == 200:
                        break # Sukses, keluar dari loop
                    else:
                        exception_msgs.append(f"Metode {i+1} respon: HTTP {r.status_code}")
                except Exception as ex:
                    exception_msgs.append(f"Metode {i+1} error: {str(ex)}")
                    continue # Abaikan error koneksi (misal timeout) lalu coba metode selanjutnya
            
            if r and r.status_code == 200:
                response = StreamingHttpResponse((chunk for chunk in r.iter_content(chunk_size=8192)), content_type='video/mp4')
                filename = f"Rekaman_Hikvision_{start_time}.mp4"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            else:
                final_status = r.status_code if r else 'Timeout/Connection-Error'
                debug_info = "\n".join(exception_msgs)
                final_text = r.text if r else f'Tidak ada respon yang valid.\n\nDetail Percobaan:\n{debug_info}'
                return HttpResponse(f"<div style='font-family:sans-serif;padding:20px'><h1>Gagal Mendownload File</h1><p><strong style='color:red'>Status Code Akhir: HTTP {final_status}</strong></p><p>Semua rute telah dicoba dan ditolak / Timeout.</p><textarea style='width:100%;height:300px;background:#f4f4f4;border:1px solid #ddd'>{final_text}</textarea></div>")
        except Exception as e:
            return HttpResponse(f"<h1>Terjadi Kesalahan Server</h1><p>{str(e)}</p>")
    
    return HttpResponse("Hanya menerima POST method.", status=400)
