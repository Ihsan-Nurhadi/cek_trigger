import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  X, Zap, DoorOpen, Lightbulb, Music, Settings,
  Power, Activity, Camera, MapPin, ChevronDown,
  Clock, FileText, CheckCircle2, AlertTriangle, Loader2, Radar, AlertCircle,
  Volume2, Play, Square, Settings2, HardDrive, Database
} from 'lucide-react'

export default function DeviceMonitorModal({ site, onClose }) {
  const navigate = useNavigate()
  const [lightStatus, setLightStatus] = useState(false)
  const [rotaryStatus, setRotaryStatus] = useState(false)
  const [activeControl, setActiveControl] = useState('floodlight')
  const [activeChannel, setActiveChannel] = useState(null)
  const [activeCamTab, setActiveCamTab] = useState(1)

  // Siren states
  const [sirenVolume, setSirenVolume] = useState(50)
  const [sirenFeedback, setSirenFeedback] = useState(null) // {type:'success'|'error', msg:''}
  const [sirenLoading, setSirenLoading] = useState(null) // channel number being triggered

  // MQTT States
  const [mqttConnected, setMqttConnected] = useState(false)
  const [doorStatus, setDoorStatus] = useState('CLOSE')
  const [plnStatus, setPlnStatus] = useState('OFF')
  const [mqttStatusTime, setMqttStatusTime] = useState('--.--.--')
  const [pirData, setPirData] = useState({
    1: { motion: 0, status: 'NO_MOTION' },
    2: { motion: 0, status: 'NO_MOTION' },
    3: { motion: 0, status: 'NO_MOTION' },
    4: { motion: 0, status: 'NO_MOTION' }
  })

  // States for Video Stream
  const [hasError, setHasError] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Reload stream timestamp when tab changes
  const [streamTime, setStreamTime] = useState(Date.now())
  
  // States for SD Card
  const [sdCardData, setSdCardData] = useState(null)

  useEffect(() => {
    setIsLoading(true)
    setHasError(false)
    setStreamTime(Date.now())
  }, [activeCamTab])

  // Polling Setup for MQTT Backend
  useEffect(() => {
    let isMounted = true

    const fetchMqttStatus = async () => {
      try {
        const res = await fetch('/api/mqtt/status/')
        if (!res.ok) throw new Error('API Error')
        const json = await res.json()
        if (json.success && json.data && json.data.NMS_002) {
          const deviceData = json.data.NMS_002
          if (isMounted) {
            setMqttConnected(true)
            if (deviceData.door) setDoorStatus(deviceData.door)
            if (deviceData.pln) setPlnStatus(deviceData.pln)
            if (deviceData.pir) setPirData(prev => ({ ...prev, ...deviceData.pir }))
            if (deviceData.last_updated) setMqttStatusTime(deviceData.last_updated)
          }
        }
      } catch (e) {
        console.error('Failed to fetch MQTT status:', e)
        if (isMounted) setMqttConnected(false)
      }
    }

    // Initial fetch
    fetchMqttStatus()

    // Poll every 2 seconds
    const intervalId = setInterval(fetchMqttStatus, 2000)

    return () => {
      isMounted = false
      clearInterval(intervalId)
    }
  }, [])

  // Polling Setup for SD Card ISAPI Status
  useEffect(() => {
    let isMounted = true
    const fetchSdCard = async () => {
      try {
        const res = await fetch(`/api/camera/sdcard/?ip=${site.ip}&username=${site.username}&password=${site.password}`)
        if (!res.ok) throw new Error('API Error')
        const json = await res.json()
        if (json.success && isMounted) {
          setSdCardData(json.hdds && json.hdds.length > 0 ? json.hdds[0] : null)
        }
      } catch (e) {
        console.error('Failed to fetch SD card status:', e)
      }
    }

    fetchSdCard()
    const intervalId = setInterval(fetchSdCard, 10000)
    return () => {
      isMounted = false
      clearInterval(intervalId)
    }
  }, [site])

  const handleTriggerSiren = async (channel) => {
    setSirenLoading(channel)
    setSirenFeedback(null)
    try {
      const res = await fetch('/api/mqtt/siren/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device: 'site_1',
          playList: channel,
          volume: sirenVolume
        })
      })
      const json = await res.json()
      if (json.success) {
        setActiveChannel(channel)
        setSirenFeedback({ type: 'success', msg: `Sirine ${channel} aktif · Vol ${sirenVolume}%` })
      } else {
        setSirenFeedback({ type: 'error', msg: json.error || 'Gagal trigger sirine.' })
      }
    } catch (e) {
      setSirenFeedback({ type: 'error', msg: 'Koneksi gagal ke server.' })
    } finally {
      setSirenLoading(null)
      // Auto-hide feedback setelah 3 detik
      setTimeout(() => setSirenFeedback(null), 3000)
    }
  }

  const handleToggleControl = async (controlType, turnOn) => {
    const stateVal = turnOn ? 1 : 0
    let cmdType = ''

    if (controlType === 'floodlight') {
      setLightStatus(turnOn)
      cmdType = 'floodlight'
    } else if (controlType === 'rotary') {
      setRotaryStatus(turnOn)
      cmdType = 'rotator'
    }

    try {
      await fetch('/api/mqtt/command/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: 'NMS_002',
          cmd: cmdType,
          state: stateVal
        })
      })
    } catch (e) {
      console.error('Failed to send command:', e)
    }
  }

  // Channel depends on tab (dummy logic: Cam 1 -> site.track_id, Cam 2 -> fallback to 102)
  const channel = activeCamTab === 1
    ? (site.track_id === '1' ? '101' : site.track_id)
    : '102'

  const streamUrl = `/stream/?channel=${channel}&t=${streamTime}`

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose}></div>

      {/* Modal Content - Dark Theme */}
      <div className="relative w-full max-w-3xl max-h-[95vh] flex flex-col bg-[#111827] text-slate-300 rounded-2xl shadow-2xl overflow-hidden border border-slate-800 animate-in fade-in zoom-in-95 duration-200">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-[#1f2937] border-b border-slate-700/50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <Zap className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h2 className="text-white font-bold">{site.name}</h2>
              <p className="text-xs text-slate-400 flex items-center gap-1">
                <MapPin className="w-3 h-3" /> {site.lat}, {site.lng} &bull; Device Control
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className={`flex items-center gap-2 px-3 py-1 border rounded-full ${mqttConnected ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-red-500/10 border-red-500/20'}`}>
              <span className={`w-2 h-2 rounded-full ${mqttConnected ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
              <span className={`text-xs font-semibold ${mqttConnected ? 'text-emerald-400' : 'text-red-400'}`}>{mqttConnected ? 'Online (MQTT)' : 'Offline'}</span>
            </div>
            <button onClick={onClose} className="p-2 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">

          {/* Site Info Accordion (Static Dummy) */}
          <div className="bg-[#1f2937] border border-slate-700/50 rounded-xl overflow-hidden">
            <div className="px-5 py-4 flex items-center justify-between border-b border-slate-700/50">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <MapPin className="w-4 h-4 text-slate-400" /> Site Info
              </h3>
              <ChevronDown className="w-4 h-4 text-slate-500" />
            </div>
            <div className="p-5 grid grid-cols-[100px_1fr] gap-y-3 text-xs">
              <span className="text-slate-500">Name</span>
              <span className="text-white font-medium">{site.name}</span>
              <span className="text-slate-500">IP Host</span>
              <span className="text-white font-medium font-mono">{site.ip}</span>
              <span className="text-slate-500">Credentials</span>
              <span className="text-white font-medium">{site.username} / ********</span>
            </div>
          </div>

          {/* DEVICE STATUS */}
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Settings className="w-4 h-4" /> Device Status
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-[#1f2937] p-4 rounded-xl border border-slate-700/50">
                <div className="flex justify-between items-start mb-3">
                  <Zap className={`w-5 h-5 ${plnStatus === 'ON' ? 'text-emerald-400' : 'text-slate-400'}`} />
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${plnStatus === 'ON' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-700 text-slate-300'}`}>{plnStatus === 'ON' ? 'Active' : 'Inactive'}</span>
                </div>
                <h4 className="text-white text-sm font-bold">PLN</h4>
                <p className="text-xs text-slate-400 mt-1">Power Supply</p>
                <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center justify-between text-[10px] text-slate-500">
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${plnStatus === 'ON' ? 'bg-emerald-500' : 'bg-slate-500'}`}></span> {plnStatus === 'ON' ? 'Device is operational' : 'Device is offline'}
                  </div>
                  <span className="font-mono text-slate-400">{mqttStatusTime}</span>
                </div>
              </div>

              <div className="bg-[#1f2937] p-4 rounded-xl border border-slate-700/50">
                <div className="flex justify-between items-start mb-3">
                  <DoorOpen className={`w-5 h-5 ${doorStatus === 'OPEN' ? 'text-red-400' : 'text-slate-400'}`} />
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${doorStatus === 'OPEN' ? 'bg-red-500/10 text-red-500' : 'bg-slate-700 text-slate-300'}`}>{doorStatus === 'OPEN' ? 'Opened' : 'Closed'}</span>
                </div>
                <h4 className="text-white text-sm font-bold">Door Panel</h4>
                <p className="text-xs text-slate-400 mt-1">Access Control</p>
                <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center justify-between text-[10px] text-slate-500">
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${doorStatus === 'OPEN' ? 'bg-red-500' : 'bg-slate-500'}`}></span> {doorStatus === 'OPEN' ? 'Open (Unsafe)' : 'Closed (Safe)'}
                  </div>
                  <span className="font-mono text-slate-400">{mqttStatusTime}</span>
                </div>
              </div>

              <div className="bg-[#1f2937] p-4 rounded-xl border border-slate-700/50">
                <div className="flex justify-between items-start mb-3">
                  <Activity className="w-5 h-5 text-emerald-400" />
                  <span className="text-[10px] font-bold px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded-sm">Not Detected</span>
                </div>
                <h4 className="text-white text-sm font-bold">Vibration Sensor</h4>
                <p className="text-xs text-slate-400 mt-1">Structural Monitoring</p>
                <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center gap-2 text-[10px] text-slate-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> No vibration activity
                </div>
              </div>

              {[1, 2, 3, 4].map(id => {
                const pd = pirData[id] || { motion: 0, status: 'NO_MOTION' };
                const isMotion = pd.motion === 1 || pd.status === 'MOTION';
                return (
                  <div key={id} className="bg-[#1f2937] p-4 rounded-xl border border-slate-700/50">
                    <div className="flex justify-between items-start mb-3">
                      <Radar className={`w-5 h-5 ${isMotion ? 'text-red-400' : 'text-emerald-400'}`} />
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${isMotion ? 'bg-red-500/10 text-red-500' : 'bg-emerald-500/10 text-emerald-400'}`}>
                        {isMotion ? 'Detected' : 'Not Detected'}
                      </span>
                    </div>
                    <h4 className="text-white text-sm font-bold">PIR Sensor {id}</h4>
                    <p className="text-xs text-slate-400 mt-1">Body Heat Detection</p>
                    <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center justify-between text-[10px] text-slate-500">
                      <div className="flex items-center gap-2">
                        <span className={`w-1.5 h-1.5 rounded-full ${isMotion ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`}></span>
                        {isMotion ? 'Motion Detected' : 'Standby'}
                      </div>
                      <span className="font-mono text-slate-400">{mqttStatusTime}</span>
                    </div>
                  </div>
                );
              })}
              
              {/* SD CARD HEALTH */}
              {sdCardData && (
                <div className="bg-[#1f2937] p-4 rounded-xl border border-slate-700/50">
                  <div className="flex justify-between items-start mb-3">
                    <Database className={`w-5 h-5 ${sdCardData.status.toLowerCase() === 'ok' ? 'text-emerald-400' : 'text-red-400'}`} />
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${sdCardData.status.toLowerCase() === 'ok' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-500'}`}>
                      {sdCardData.status.toLowerCase() === 'ok' ? 'Healthy' : 'Error'}
                    </span>
                  </div>
                  <h4 className="text-white text-sm font-bold">Storage Health</h4>
                  <p className="text-[10px] text-slate-400 mt-1 uppercase">CAMERA SD/HDD</p>
                  <div className="mt-3 pt-3 border-t border-slate-700/50 flex flex-col gap-1.5 text-[10px] text-slate-500">
                    <div className="w-full bg-slate-800 rounded-full h-1.5 mt-1 overflow-hidden border border-slate-700">
                      <div 
                        className={`h-1.5 rounded-full ${((sdCardData.capacity - sdCardData.freeSpace) / sdCardData.capacity) > 0.9 ? 'bg-red-500' : 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'}`}
                        style={{ width: `${Math.max(0, Math.min(100, ((sdCardData.capacity - sdCardData.freeSpace) / sdCardData.capacity) * 100))}%` }}
                      ></div>
                    </div>
                    <div className="flex justify-between w-full mt-0.5">
                      <span>Used <span className="text-slate-300 font-mono">{((sdCardData.capacity - sdCardData.freeSpace) / 1024).toFixed(1)}GB</span></span>
                      <span>Total <span className="text-slate-300 font-mono">{(sdCardData.capacity / 1024).toFixed(1)}GB</span></span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* DEVICE CONTROL */}
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Settings className="w-4 h-4" /> Device Control
            </h3>

            {/* Floodlight & Rotary Box */}
            <div className="bg-[#1f2937] rounded-xl border border-slate-700/50 p-5 mb-3 flex flex-col md:flex-row gap-6 items-center">
              <div className="flex gap-4">
                <div
                  className="flex flex-col items-center gap-2 cursor-pointer group"
                  onClick={() => setActiveControl('floodlight')}
                >
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center border transition-all ${activeControl === 'floodlight' ? 'ring-2 ring-emerald-500 ring-offset-2 ring-offset-[#1f2937]' : ''} ${lightStatus ? 'bg-orange-500/20 border-orange-500/50 text-orange-400' : 'bg-slate-800 border-slate-700 text-slate-500 group-hover:bg-slate-800/80'}`}>
                    <Lightbulb className="w-5 h-5" />
                  </div>
                  <span className={`text-[10px] ${activeControl === 'floodlight' ? 'text-white font-bold' : 'text-slate-400'}`}>Floodlight</span>
                </div>
                <div
                  className="flex flex-col items-center gap-2 cursor-pointer group"
                  onClick={() => setActiveControl('rotary')}
                >
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center border transition-all ${activeControl === 'rotary' ? 'ring-2 ring-emerald-500 ring-offset-2 ring-offset-[#1f2937]' : ''} ${rotaryStatus ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'bg-slate-800 border-slate-700 text-slate-500 group-hover:bg-slate-800/80'}`}>
                    <Settings className="w-5 h-5" />
                  </div>
                  <span className={`text-[10px] ${activeControl === 'rotary' ? 'text-white font-bold' : 'text-slate-400'}`}>Rotary</span>
                </div>
              </div>

              <div className="flex-1 w-full space-y-2">
                <div
                  className={`flex items-center justify-between px-4 py-2 rounded-lg text-xs cursor-pointer transition border ${activeControl === 'floodlight' ? 'bg-slate-700/50 border-slate-600' : 'bg-slate-800/50 border-transparent hover:bg-slate-700/30'}`}
                  onClick={() => setActiveControl('floodlight')}
                >
                  <span className="flex items-center gap-2"><Lightbulb className={`w-3 h-3 ${activeControl === 'floodlight' ? 'text-emerald-400' : 'text-slate-500'}`} /> Floodlight</span>
                  <span className={lightStatus ? 'text-orange-400 font-bold' : 'text-slate-400'}>{lightStatus ? 'On' : 'Off'}</span>
                </div>
                <div
                  className={`flex items-center justify-between px-4 py-2 rounded-lg text-xs cursor-pointer transition border ${activeControl === 'rotary' ? 'bg-slate-700/50 border-slate-600' : 'bg-slate-800/50 border-transparent hover:bg-slate-700/30'}`}
                  onClick={() => setActiveControl('rotary')}
                >
                  <span className="flex items-center gap-2"><Settings className={`w-3 h-3 ${activeControl === 'rotary' ? 'text-emerald-400' : 'text-slate-500'}`} /> Rotary Motor</span>
                  <span className={rotaryStatus ? 'text-indigo-400 font-bold' : 'text-slate-400'}>{rotaryStatus ? 'On' : 'Off'}</span>
                </div>
              </div>

              <div className="flex md:flex-col w-full md:w-32 gap-2">
                <button
                  onClick={() => handleToggleControl(activeControl, true)}
                  className={`py-2 rounded-lg text-xs font-bold transition flex-1 ${(activeControl === 'floodlight' && lightStatus) || (activeControl === 'rotary' && rotaryStatus)
                    ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/20'
                    : 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                    }`}
                >
                  <Power className="w-3 h-3 inline mr-1" /> Turn ON
                </button>
                <button
                  onClick={() => handleToggleControl(activeControl, false)}
                  className={`py-2 rounded-lg text-xs font-bold transition flex-1 ${(activeControl === 'floodlight' && !lightStatus) || (activeControl === 'rotary' && !rotaryStatus)
                    ? 'bg-slate-700 text-white'
                    : 'bg-[#1f2937] border border-slate-700 text-slate-400 hover:bg-slate-800'
                    }`}
                >
                  <Power className="w-3 h-3 inline mr-1" /> Turn OFF
                </button>
              </div>
            </div>

            {/* Siren Control */}
            <div className="bg-[#1f2937] rounded-xl border border-slate-700/50 p-5">
              {/* Header */}
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-indigo-500/10">
                    <Music className="w-4 h-4 text-indigo-400" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Audio Control</h4>
                    <p className="text-[10px] text-slate-400">Select audio channel</p>
                  </div>
                </div>
                {/* Volume badge */}
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-indigo-400 font-bold">{sirenVolume}%</span>
                  <div className="p-1.5 rounded-lg bg-indigo-500/10">
                    <Volume2 className="w-4 h-4 text-indigo-400" />
                  </div>
                </div>
              </div>

              {/* Volume Slider */}
              <div className="mb-4 px-1">
                <div className="flex items-center justify-between mb-1.5 text-[10px] text-slate-400">
                  <span>Volume</span>
                  <span className="text-indigo-400 font-bold">{sirenVolume}%</span>
                </div>
                <div className="flex items-center gap-2">
                  <Volume2 className="w-3.5 h-3.5 text-slate-500 shrink-0" style={{opacity: 0.4}} />
                  <input
                    id="siren-volume-slider"
                    type="range"
                    min="0"
                    max="100"
                    value={sirenVolume}
                    onChange={e => setSirenVolume(Number(e.target.value))}
                    className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, #818cf8 0%, #818cf8 ${sirenVolume}%, #334155 ${sirenVolume}%, #334155 100%)`,
                      accentColor: '#818cf8'
                    }}
                  />
                  <Volume2 className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                </div>
              </div>

              {/* Feedback Toast */}
              {sirenFeedback && (
                <div className={`mb-3 px-3 py-2 rounded-lg text-[11px] font-semibold flex items-center gap-2 ${
                  sirenFeedback.type === 'success'
                    ? 'bg-indigo-500/15 border border-indigo-500/30 text-indigo-300'
                    : 'bg-red-500/15 border border-red-500/30 text-red-400'
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    sirenFeedback.type === 'success' ? 'bg-indigo-400' : 'bg-red-400'
                  }`} />
                  {sirenFeedback.msg}
                </div>
              )}

              {/* Channel Buttons */}
              <div className="grid grid-cols-3 gap-2">
                {[1, 2, 3, 4, 5, 6].map(ch => (
                  <button
                    key={ch}
                    id={`siren-btn-${ch}`}
                    onClick={() => handleTriggerSiren(ch)}
                    disabled={sirenLoading === ch}
                    className={`py-3 rounded-lg text-xs font-semibold flex flex-col items-center gap-1.5 transition border relative overflow-hidden ${
                      activeChannel === ch
                        ? 'bg-indigo-500/25 border-indigo-500/60 text-indigo-300 shadow-[0_0_12px_rgba(99,102,241,0.25)]'
                        : 'bg-slate-800/50 border-slate-700/50 text-slate-400 hover:border-indigo-500/40 hover:text-indigo-300 hover:bg-indigo-500/10'
                    }`}
                  >
                    {sirenLoading === ch ? (
                      <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.3"/>
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>
                      </svg>
                    ) : (
                      <Music className="w-4 h-4" />
                    )}
                    {ch}
                  </button>
                ))}
              </div>

              {/* Active Channel Footer */}
              <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center justify-between text-[10px] text-slate-500">
                <div className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${activeChannel ? 'bg-indigo-400 animate-pulse' : 'bg-slate-600'}`} />
                  {activeChannel ? 'Active Channel' : 'No channel active'}
                </div>
                {activeChannel && (
                  <span className="font-mono text-indigo-400 font-bold">{activeChannel}</span>
                )}
              </div>
            </div>
          </div>

          {/* CCTV CAMERAS (Integrated from previous LiveStreamModal) */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                <Camera className="w-4 h-4" /> CCTV Cameras <span className="normal-case tracking-normal">- Human Motion Detection</span>
              </h3>
              <span className="flex items-center gap-1 text-[10px] font-bold text-red-500">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></span> LIVE
              </span>
            </div>

            <div className="bg-[#1f2937] rounded-xl border border-slate-700/50 overflow-hidden">
              {/* Tabs */}
              <div className="flex border-b border-slate-700/50">
                <button
                  onClick={() => setActiveCamTab(1)}
                  className={`flex-1 py-3 px-4 flex justify-between items-center text-xs font-semibold transition ${activeCamTab === 1 ? 'bg-slate-800/80 text-white border-b-2 border-emerald-500' : 'text-slate-400 hover:bg-slate-800/50'}`}
                >
                  <span className="flex items-center gap-2"><Camera className="w-3 h-3" /> Camera </span>
                </button>
              </div>

              {/* Video Stream Container */}
              <div className="relative aspect-video bg-black flex items-center justify-center p-1">
                {/* OSD Info Overlay */}
                <div className="absolute top-4 left-4 z-20 flex items-center gap-2 text-xs font-mono text-white/80 drop-shadow-md">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span> CAM-0{activeCamTab} — Main Entrance
                </div>
                <div className="absolute top-4 right-4 z-20 text-xs font-mono text-white/80 drop-shadow-md">
                  {new Date().toLocaleTimeString('en-US', { hour12: false })}
                </div>

                <div className="absolute bottom-4 left-4 z-20">
                  <span className="px-2 py-1 bg-green-500/20 border border-green-500 text-green-400 text-[10px] font-bold rounded-md backdrop-blur-md flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Area Clear
                  </span>
                </div>
                <div className="absolute bottom-4 right-4 z-20 text-xs font-mono text-white/80 drop-shadow-md">
                  1080p HD
                </div>

                {isLoading && !hasError && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-white/70 bg-slate-900/50 z-10">
                    <Loader2 className="animate-spin w-8 h-8 mb-3 text-emerald-500" />
                    <p className="font-mono text-xs tracking-widest text-emerald-400/80">CONNECTING TO CAMERA...</p>
                  </div>
                )}

                {!hasError ? (
                  <img
                    src={streamUrl}
                    className="w-full h-full object-contain relative z-10"
                    alt={`Stream Camera ${activeCamTab}`}
                    onLoad={() => setIsLoading(false)}
                    onError={() => {
                      setIsLoading(false)
                      setHasError(true)
                    }}
                  />
                ) : (
                  <div className="text-center p-8 z-10 w-full h-full flex flex-col items-center justify-center bg-slate-900">
                    <AlertCircle className="w-12 h-12 text-red-500/80 mb-3" />
                    <p className="text-slate-300 font-medium text-sm">Connection Failed</p>
                    <p className="text-slate-500 text-xs mt-1">Cannot reach camera stream on Ch{channel}.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer Area */}
        <div className="px-6 py-4 bg-[#1f2937] border-t border-slate-700/50 shrink-0 flex items-center justify-between text-xs">
          <div className="text-slate-500 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Last synced: just now
          </div>
          <div className="flex gap-3">
            <button 
              onClick={() => navigate(`/history?site_id=${site.id}`)}
              className="flex items-center gap-2 px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition font-medium border border-slate-700"
            >
              <FileText className="w-4 h-4" /> Site Detail
            </button>
            <a
              href={`/logs-history/?ip=${site.ip}&username=${site.username}&password=${site.password}&track_id=${site.track_id}&autoload=1`}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg hover:bg-emerald-500/20 transition font-medium no-underline"
            >
              <FileText className="w-4 h-4" /> Site Record
            </a>
          </div>
        </div>

      </div>
    </div>
  )
}
