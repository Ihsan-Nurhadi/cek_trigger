import { useState, useEffect } from 'react'
import { X, Activity, BellOff, BellRing } from 'lucide-react'

export default function NotificationSidebar({ isOpen, onClose }) {
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [sseStatus, setSseStatus] = useState('connecting')
  const [toasts, setToasts] = useState([])

  const playNotificationSound = () => {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext
      if (!AudioContext) return
      const audioCtx = new AudioContext()
      const playTone = (freq, startTime, duration) => {
        const osc = audioCtx.createOscillator()
        const gain = audioCtx.createGain()
        osc.connect(gain)
        gain.connect(audioCtx.destination)
        osc.type = 'sine'
        osc.frequency.value = freq
        gain.gain.setValueAtTime(0, startTime)
        gain.gain.linearRampToValueAtTime(0.3, startTime + 0.05)
        gain.gain.linearRampToValueAtTime(0, startTime + duration)
        osc.start(startTime)
        osc.stop(startTime + duration)
      }
      const now = audioCtx.currentTime
      playTone(880, now, 0.15) // A5
      playTone(1108.73, now + 0.12, 0.3) // C#6
    } catch(e) { console.warn("Audio disabled or not supported", e) }
  }

  const loadInitial = async () => {
    try {
      const res = await fetch('/notifications/')
      const data = await res.json()
      setNotifications(data.notifications || [])
      setUnreadCount(data.unread_count || 0)
    } catch (e) {
      console.error(e)
    }
  }

  const markAllRead = async () => {
    try {
      await fetch('/notifications/mark-read/', { method: 'POST' })
      loadInitial()
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    loadInitial()

    const evtSource = new EventSource('/notifications/sse/')
    evtSource.onopen = () => setSseStatus('connected')
    
    evtSource.onmessage = e => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'connected') return

        setNotifications(prev => {
          const updated = [data, ...prev].slice(0, 20)
          setUnreadCount(updated.filter(n => !n.is_read).length)
          return updated
        })

        // Also show Toast and play sound
        const newToast = { ...data, toastId: Date.now() + Math.random() }
        setToasts(prev => [...prev, newToast])
        playNotificationSound()
        
        setTimeout(() => {
          setToasts(prev => prev.filter(t => t.toastId !== newToast.toastId))
        }, 5000)
      } catch (err) {}
    }

    evtSource.onerror = () => setSseStatus('error')

    return () => evtSource.close()
  }, [])

  return (
    <>
    <div className={`fixed top-[80px] right-0 w-[340px] h-[calc(100vh-80px)] bg-slate-900/95 backdrop-blur-xl border-l border-indigo-500/25 z-[900] flex flex-col transition-transform duration-300 shadow-2xl ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}>
      <div className="px-4 py-4 flex items-center justify-between border-b border-white/10 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
          <span className="text-white font-bold text-sm tracking-wide">Notifikasi Live</span>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white transition p-1">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="px-4 py-3 bg-white/5 border-b border-white/5 shrink-0 flex items-center justify-between">
        <span className="text-slate-400 text-xs">Total: <span className="text-white font-semibold">{notifications.length}</span></span>
        <span className="text-slate-400 text-xs">Belum dibaca: <span className="text-red-400 font-semibold">{unreadCount}</span></span>
        <button onClick={markAllRead} className="text-indigo-400 text-xs hover:text-indigo-300 transition">Bersihkan</button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {notifications.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm">
            <BellOff className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p>Menunggu motion event...</p>
          </div>
        ) : (
          notifications.map(n => (
            <div key={n.id} className={`px-4 py-3 border-l-4 transition-colors hover:bg-white/5 ${n.event_type === 'motion_start' ? 'border-red-500' : 'border-green-500'} ${!n.is_read ? 'bg-indigo-500/10' : ''}`}>
              <div className="flex items-start gap-2">
                <div className="mt-1">
                  {n.event_type === 'motion_start' ? <Activity className="w-4 h-4 text-red-500" /> : <Activity className="w-4 h-4 text-green-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-xs font-semibold">{n.event_type === 'motion_start' ? 'Motion Terdeteksi' : 'Motion Berhenti'}</p>
                  <p className="text-slate-400 text-xs mt-0.5">📍 {n.site_name}</p>
                  <p className="text-slate-500 text-xs border-t border-white/5 mt-1 pt-1">{n.timestamp}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="px-4 py-3 border-t border-white/10 shrink-0 flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${sseStatus === 'connected' ? 'bg-green-500' : 'bg-red-500'}`}></div>
        <span className={`text-xs ${sseStatus === 'connected' ? 'text-green-500' : 'text-red-500'}`}>
          {sseStatus === 'connected' ? 'Terhubung (live)' : 'Menghubungkan...'}
        </span>
      </div>
    </div>

    {/* OVERLAY TOASTS */}
    <div className="fixed top-6 left-1/2 -translate-x-1/2 z-[2000] flex flex-col gap-3 pointer-events-none">
      {toasts.map(t => (
        <div key={t.toastId} className="bg-slate-900/95 backdrop-blur-md border border-indigo-500/30 rounded-xl px-5 py-3 text-white shadow-2xl flex items-center gap-3 animate-in slide-in-from-top-10 fade-in duration-300 pointer-events-auto">
          <div className="text-[20px] leading-none">{t.event_type === 'motion_start' ? '🔴' : '🟢'}</div>
          <div>
            <p className="font-bold text-sm m-0 leading-tight">{t.event_type === 'motion_start' ? 'Motion Terdeteksi' : 'Motion Berhenti'}</p>
            <p className="text-xs text-slate-300 m-0 mt-0.5 leading-tight">{t.site_name} (Ch {t.channel})</p>
          </div>
        </div>
      ))}
    </div>
    </>
  )
}
