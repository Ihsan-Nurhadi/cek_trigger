import { useState, useEffect } from 'react'
import { X, Video, Loader2, AlertCircle } from 'lucide-react'

export default function LiveStreamModal({ site, onClose }) {
  const [hasError, setHasError] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Use timestamp to prevent caching
  const streamUrl = `/stream/?channel=${site.track_id === '1' ? '101' : site.track_id}&t=${Date.now()}`

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl overflow-hidden w-full max-w-4xl max-h-[90vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
        
        <div className="px-6 py-4 flex justify-between items-center border-b border-gray-100 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 rounded-lg">
              <Video className="w-5 h-5 text-red-600 animate-pulse" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-800">Live View: {site.name}</h2>
              <p className="text-xs text-gray-400 font-mono">IP: {site.ip}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-red-500 hover:bg-red-50 p-2 rounded-full transition">
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="relative bg-slate-950 flex-grow min-h-[400px] flex items-center justify-center overflow-hidden">
          {isLoading && !hasError && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-white/70">
              <Loader2 className="animate-spin w-10 h-10 mb-4 text-blue-500" />
              <p className="font-mono text-sm tracking-widest text-blue-400/80">CONNECTING TO CAMERA...</p>
            </div>
          )}

          {!hasError ? (
            <img 
              src={streamUrl}
              className="w-full max-h-full object-contain relative z-10"
              alt="Video Stream"
              onLoad={() => setIsLoading(false)}
              onError={() => {
                setIsLoading(false)
                setHasError(true)
              }}
            />
          ) : (
            <div className="text-center p-8">
              <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4 opacity-80" />
              <p className="text-white font-medium mb-1">Conection Failed</p>
              <p className="text-slate-400 text-sm">Cannot reach camera stream. Please check configuration.</p>
            </div>
          )}
        </div>

        {hasError && (
          <div className="bg-red-50 flex-shrink-0 text-red-700 px-6 py-3 text-sm font-semibold text-center border-t border-red-200">
            Gagal memuat video stream. Pastikan kamera menyala dan dapat diakses.
          </div>
        )}
      </div>
    </div>
  )
}
