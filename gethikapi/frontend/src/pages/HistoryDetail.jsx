import { useState, useEffect } from 'react'
import { ArrowLeft, Calendar, Download, Eye, Camera, Radar, Shield } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

export default function HistoryDetail({ onBack }) {
  const [searchParams] = useSearchParams()
  const initialSiteId = searchParams.get('site_id') || ''

  const [data, setData] = useState({ camera_history: [], pir_history: [] })
  const [loading, setLoading] = useState(true)
  const [siteId, setSiteId] = useState(initialSiteId)
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  
  const [photoViewer, setPhotoViewer] = useState({ isOpen: false, url: '', title: '' })

  const fetchHistory = async () => {
    setLoading(true)
    try {
      let url = '/api/history/snapshots/?'
      if (siteId) url += `site_id=${siteId}&`
      if (startTime) url += `start_time=${startTime}&`
      if (endTime) url += `end_time=${endTime}&`
      
      const res = await fetch(url)
      const json = await res.json()
      if (json.success) {
        setData(json)
      }
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchHistory()
  }, [])

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0f172a]">
      {/* Header */}
      <header className="bg-[#1e293b] border-b border-slate-700/50 py-4 px-6 flex flex-col md:flex-row md:items-center justify-between gap-4 sticky top-0 z-10 shrink-0 shadow-lg">
        <div className="flex items-center gap-4">
          <button 
            onClick={onBack}
            className="flex items-center justify-center p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-bold text-white flex items-center gap-2">
              <Shield className="w-5 h-5 text-indigo-400" />
              Recording & Snapshot History
            </h1>
            <p className="text-xs text-slate-400 font-mono">System Events Log</p>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-1.5 focus-within:border-indigo-500 transition">
            <Calendar className="w-4 h-4 text-slate-400" />
            <input 
              type="datetime-local" 
              value={startTime}
              onChange={e => setStartTime(e.target.value)}
              className="bg-transparent text-xs text-slate-200 outline-none w-[140px]" 
            />
          </div>
          <span className="text-slate-500 text-xs">to</span>
          <div className="flex items-center gap-2 bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-1.5 focus-within:border-indigo-500 transition">
            <Calendar className="w-4 h-4 text-slate-400" />
            <input 
              type="datetime-local" 
              value={endTime}
              onChange={e => setEndTime(e.target.value)}
              className="bg-transparent text-xs text-slate-200 outline-none w-[140px]" 
            />
          </div>
          <button 
            onClick={fetchHistory}
            className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-4 py-2.5 rounded-lg transition shadow-lg shadow-indigo-500/20"
          >
            Filter
          </button>
        </div>
      </header>

      {/* Main Content: Split Tables */}
      <main className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="font-mono text-sm">LOADING HISTORY DATA...</p>
          </div>
        ) : (
          <div className="grid lg:grid-cols-2 gap-6 h-full items-start">
            
            {/* Table 1: Camera Motion */}
            <div className="bg-[#1e293b] rounded-2xl border border-slate-700/50 shadow-xl overflow-hidden flex flex-col max-h-full">
              <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50 flex items-center justify-between shrink-0">
                <h2 className="text-sm font-bold text-white flex items-center gap-2 uppercase tracking-wide">
                  <Camera className="w-4 h-4 text-orange-400" />
                  Camera Motion Detect
                </h2>
                <span className="bg-orange-500/10 text-orange-400 text-[10px] font-bold px-2 py-1 rounded-md">
                  {data.camera_history.length} Records
                </span>
              </div>
              <div className="overflow-auto grow custom-scrollbar p-0">
                <table className="w-full text-left border-collapse min-w-[400px]">
                  <thead className="bg-[#0f172a]/50 sticky top-0 z-10 backdrop-blur-md">
                    <tr>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider w-[50px] text-center">No</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Date History</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">History Item</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {data.camera_history.length === 0 ? (
                      <tr>
                        <td colSpan="4" className="px-4 py-12 text-center text-slate-500 text-xs italic">
                          No camera motion recorded.
                        </td>
                      </tr>
                    ) : (data.camera_history.map((item, idx) => (
                      <tr key={item.id} className="hover:bg-slate-800/30 transition">
                        <td className="px-4 py-4 text-xs font-mono text-slate-500 text-center">{idx + 1}</td>
                        <td className="px-4 py-4 text-xs font-medium text-slate-300">{item.timestamp}</td>
                        <td className="px-4 py-4 text-xs font-semibold text-orange-200">
                          {item.site_name} — M-Detect
                        </td>
                        <td className="px-4 py-4 text-center">
                          <button 
                            onClick={() => setPhotoViewer({ isOpen: true, url: item.image_url, title: `Camera Motion - ${item.timestamp}` })}
                            className="inline-flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 text-[10px] font-bold px-3 py-1.5 rounded-md transition"
                          >
                            <Eye className="w-3 h-3" /> View Photo
                          </button>
                        </td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Table 2: PIR Sensor Motion */}
            <div className="bg-[#1e293b] rounded-2xl border border-slate-700/50 shadow-xl overflow-hidden flex flex-col max-h-full">
              <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50 flex items-center justify-between shrink-0">
                <h2 className="text-sm font-bold text-white flex items-center gap-2 uppercase tracking-wide">
                  <Radar className="w-4 h-4 text-emerald-400" />
                  PIR Sensor Detect
                </h2>
                <span className="bg-emerald-500/10 text-emerald-400 text-[10px] font-bold px-2 py-1 rounded-md">
                  {data.pir_history.length} Records
                </span>
              </div>
              <div className="overflow-auto grow custom-scrollbar p-0">
                <table className="w-full text-left border-collapse min-w-[400px]">
                   <thead className="bg-[#0f172a]/50 sticky top-0 z-10 backdrop-blur-md">
                    <tr>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider w-[50px] text-center">No</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Date History</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">History Item</th>
                      <th className="px-4 py-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/30">
                    {data.pir_history.length === 0 ? (
                      <tr>
                        <td colSpan="4" className="px-4 py-12 text-center text-slate-500 text-xs italic">
                          No PIR sensor motion recorded.
                        </td>
                      </tr>
                    ) : (data.pir_history.map((item, idx) => (
                      <tr key={item.id} className="hover:bg-slate-800/30 transition">
                        <td className="px-4 py-4 text-xs font-mono text-slate-500 text-center">{idx + 1}</td>
                        <td className="px-4 py-4 text-xs font-medium text-slate-300">{item.timestamp}</td>
                        <td className="px-4 py-4 text-xs font-semibold text-emerald-200">
                          {item.trigger_source} Detected (Body Heat)
                        </td>
                        <td className="px-4 py-4 text-center">
                          <button 
                            onClick={() => setPhotoViewer({ isOpen: true, url: item.image_url, title: `PIR Sensor - ${item.timestamp}` })}
                            className="inline-flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 text-[10px] font-bold px-3 py-1.5 rounded-md transition"
                          >
                            <Eye className="w-3 h-3" /> View Photo
                          </button>
                        </td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        )}
      </main>

      {/* Photo Viewer Modal */}
      {photoViewer.isOpen && (
        <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/90 backdrop-blur-sm" onClick={() => setPhotoViewer({ isOpen: false, url: '', title: '' })}></div>
          <div className="relative max-w-5xl w-full flex flex-col bg-[#0f172a] border border-slate-700 rounded-xl overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between px-4 py-3 bg-[#1e293b] border-b border-slate-700">
              <h3 className="text-white text-sm font-semibold flex items-center gap-2">
                <Camera className="w-4 h-4 text-indigo-400" />
                {photoViewer.title}
              </h3>
              <div className="flex items-center gap-2">
                <a href={photoViewer.url} download target="_blank" rel="noreferrer" className="text-slate-400 hover:text-white p-1 bg-slate-800 rounded transition" title="Download">
                  <Download className="w-4 h-4" />
                </a>
                <button onClick={() => setPhotoViewer({ isOpen: false, url: '', title: '' })} className="text-slate-400 hover:text-white p-1 bg-slate-800 rounded transition">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
            <div className="bg-black flex items-center justify-center min-h-[400px] p-2 relative">
              {/* Fallback pattern / loading UI is handled natively by img onError potentially, or just assume it loads */}
              <img 
                src={photoViewer.url} 
                alt="Snapshot" 
                className="max-w-full max-h-[80vh] object-contain rounded"
                onError={(e) => { e.target.onerror = null; e.target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="100%" height="100%" fill="%231e293b"/><text x="50%" y="50%" fill="%2394a3b8" font-family="sans-serif" font-size="14" text-anchor="middle">Image Not Found / Error</text></svg>' }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
