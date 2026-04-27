import { useState, useEffect } from 'react'
import { Settings, X, Plus, Trash2, Power, PowerOff, Pencil, Check, XCircle } from 'lucide-react'

export default function SiteModal({ isOpen, onClose, sites, reloadSites }) {
  // ── State form tambah site baru ──────────────────────────
  const [formData, setFormData] = useState({
    name: '', ip: '', port: '80', username: '', password: '', track_id: '1', lat: '', lng: ''
  })
  const [msg, setMsg] = useState(null)

  // ── State edit site ───────────────────────────────────────
  const [editingId, setEditingId] = useState(null)   // ID site yang sedang diedit
  const [editData, setEditData] = useState({})        // Data form edit
  const [editMsg, setEditMsg] = useState(null)

  // ── Buka form edit: isi dengan data site saat ini ────────
  const startEdit = (site) => {
    setEditingId(site.id)
    setEditData({
      name: site.name,
      ip: site.ip,
      port: String(site.port),
      username: site.username,
      password: site.password,
      track_id: site.track_id,
      lat: String(site.lat),
      lng: String(site.lng),
    })
    setEditMsg(null)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditData({})
    setEditMsg(null)
  }

  // ── Simpan perubahan edit ─────────────────────────────────
  const handleUpdate = async (id) => {
    if (!editData.name || !editData.ip || !editData.username) {
      setEditMsg({ type: 'error', text: 'Nama, IP, dan Username wajib diisi.' })
      return
    }
    try {
      const res = await fetch(`/sites/${id}/update/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editData)
      })
      const data = await res.json()
      if (data.success) {
        setEditMsg({ type: 'success', text: 'Berhasil disimpan!' })
        reloadSites()
        setTimeout(() => { setEditingId(null); setEditMsg(null) }, 800)
      } else {
        setEditMsg({ type: 'error', text: data.error || 'Gagal menyimpan.' })
      }
    } catch (e) {
      setEditMsg({ type: 'error', text: 'Terjadi kesalahan sistem.' })
    }
  }

  // ── Tambah site baru ──────────────────────────────────────
  const handleAdd = async () => {
    if (!formData.name || !formData.ip || !formData.username || !formData.password) {
      setMsg({ type: 'error', text: 'Nama, IP, Username, dan Password wajib diisi.' })
      return
    }
    try {
      const res = await fetch('/sites/add/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      const data = await res.json()
      if (data.success) {
        setMsg({ type: 'success', text: 'Site berhasil ditambahkan!' })
        setFormData({ name: '', ip: '', port: '80', username: '', password: '', track_id: '1', lat: '', lng: '' })
        reloadSites()
      } else {
        setMsg({ type: 'error', text: data.error || 'Gagal menambahkan site.' })
      }
    } catch (e) {
      setMsg({ type: 'error', text: 'Terjadi kesalahan sistem.' })
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Hapus site ini? Monitor akan dihentikan.')) return
    try {
      const res = await fetch(`/sites/${id}/delete/`, { method: 'POST' })
      const data = await res.json()
      if (data.success) { cancelEdit(); reloadSites() }
      else alert('Gagal menghapus: ' + data.error)
    } catch (e) { console.error(e) }
  }

  const handleToggle = async (id) => {
    try {
      const res = await fetch(`/sites/${id}/toggle/`, { method: 'POST' })
      const data = await res.json()
      if (data.success) reloadSites()
      else alert('Gagal mengubah status: ' + data.error)
    } catch (e) { console.error(e) }
  }

  if (!isOpen) return null

  // ── Helper: input style ───────────────────────────────────
  const inputCls = "w-full bg-white/5 border border-white/10 rounded-lg text-slate-200 px-3 py-2 text-sm focus:border-indigo-500 outline-none"
  const labelCls = "block text-[11px] text-slate-400 mb-1 font-medium"

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/75 backdrop-blur-sm">
      <div className="w-full max-w-lg mx-4 rounded-2xl overflow-hidden shadow-2xl bg-slate-900 border border-indigo-500/25">

        {/* Header */}
        <div className="px-6 py-5 flex items-center justify-between border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/20 rounded-lg">
              <Settings className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-white font-bold text-lg">Kelola Site Kamera</h2>
              <p className="text-slate-400 text-xs">Maksimal 2 site kamera</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[75vh]">

          {/* ── Daftar Site ── */}
          <div className="mb-6">
            <h3 className="text-slate-300 text-xs font-semibold uppercase tracking-wider mb-3">Site Terdaftar</h3>
            <div className="space-y-3">
              {sites.length === 0 ? (
                <p className="text-slate-500 text-sm text-center py-4">Belum ada site terdaftar.</p>
              ) : (
                sites.map(s => (
                  <div key={s.id} className="rounded-xl border border-white/5 bg-white/5 overflow-hidden">

                    {/* Baris ringkasan site */}
                    <div className="flex items-center gap-3 px-4 py-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-white font-semibold text-sm truncate">{s.name}</p>
                        <p className="text-slate-400 text-xs">{s.ip}:{s.port} · lat {s.lat}, lng {s.lng}</p>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded-full font-semibold ${s.is_active ? 'bg-green-500/20 text-green-400' : 'bg-slate-500/20 text-slate-400'}`}>
                        {s.is_active ? 'Aktif' : 'Nonaktif'}
                      </span>
                      {/* Tombol Edit */}
                      <button
                        onClick={() => editingId === s.id ? cancelEdit() : startEdit(s)}
                        className={`transition p-1 rounded ${editingId === s.id ? 'text-indigo-400 bg-indigo-500/20' : 'text-slate-400 hover:text-indigo-400'}`}
                        title="Edit Site"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleToggle(s.id)} className="text-slate-400 hover:text-indigo-400 transition p-1" title="Toggle Monitor">
                        {s.is_active ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
                      </button>
                      <button onClick={() => handleDelete(s.id)} className="text-slate-400 hover:text-red-400 transition p-1" title="Hapus Site">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Form Edit (collapsible) */}
                    {editingId === s.id && (
                      <div className="px-4 pb-4 border-t border-white/10 pt-3">
                        {editMsg && (
                          <div className={`mb-3 px-3 py-2 rounded-lg text-xs font-semibold ${editMsg.type === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>
                            {editMsg.text}
                          </div>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                          {/* Nama */}
                          <div className="col-span-2">
                            <label className={labelCls}>Nama Site *</label>
                            <input value={editData.name} onChange={e => setEditData({...editData, name: e.target.value})} type="text" className={inputCls} />
                          </div>
                          {/* IP & Port */}
                          <div>
                            <label className={labelCls}>IP Kamera *</label>
                            <input value={editData.ip} onChange={e => setEditData({...editData, ip: e.target.value})} type="text" className={inputCls} />
                          </div>
                          <div>
                            <label className={labelCls}>Port</label>
                            <input value={editData.port} onChange={e => setEditData({...editData, port: e.target.value})} type="number" className={inputCls} />
                          </div>
                          {/* Username & Password */}
                          <div>
                            <label className={labelCls}>Username *</label>
                            <input value={editData.username} onChange={e => setEditData({...editData, username: e.target.value})} type="text" className={inputCls} />
                          </div>
                          <div>
                            <label className={labelCls}>Password</label>
                            <input value={editData.password} onChange={e => setEditData({...editData, password: e.target.value})} type="password" className={inputCls} placeholder="Kosongkan jika tidak diubah" />
                          </div>
                          {/* Track ID */}
                          <div>
                            <label className={labelCls}>Track ID</label>
                            <input value={editData.track_id} onChange={e => setEditData({...editData, track_id: e.target.value})} type="text" className={inputCls} />
                          </div>
                          <div /> {/* spacer */}
                          {/* Lat & Lng */}
                          <div>
                            <label className={labelCls}>Latitude</label>
                            <input value={editData.lat} onChange={e => setEditData({...editData, lat: e.target.value})} type="number" step="any" className={inputCls} placeholder="-6.2088" />
                          </div>
                          <div>
                            <label className={labelCls}>Longitude</label>
                            <input value={editData.lng} onChange={e => setEditData({...editData, lng: e.target.value})} type="number" step="any" className={inputCls} placeholder="106.8456" />
                          </div>
                        </div>
                        {/* Tombol Simpan / Batal */}
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => handleUpdate(s.id)}
                            className="flex-1 bg-gradient-to-r from-indigo-600 to-blue-600 text-white font-semibold py-2 rounded-xl flex items-center justify-center gap-2 text-sm hover:opacity-85 transition"
                          >
                            <Check className="w-4 h-4" /> Simpan
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="flex-1 bg-white/5 border border-white/10 text-slate-300 font-semibold py-2 rounded-xl flex items-center justify-center gap-2 text-sm hover:bg-white/10 transition"
                          >
                            <XCircle className="w-4 h-4" /> Batal
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* ── Form Tambah Site Baru ── */}
          <div>
            <h3 className="text-slate-300 text-xs font-semibold uppercase tracking-wider mb-3">Tambah Site Baru</h3>
            {msg && (
              <div className={`mb-3 px-3 py-2 rounded-lg text-xs font-semibold ${msg.type === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>
                {msg.text}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className={labelCls}>Nama Site *</label>
                <input value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} type="text" className={inputCls} placeholder="Site Kantor" />
              </div>
              <div>
                <label className={labelCls}>IP Kamera *</label>
                <input value={formData.ip} onChange={e => setFormData({...formData, ip: e.target.value})} type="text" className={inputCls} placeholder="192.168.1.100" />
              </div>
              <div>
                <label className={labelCls}>Port</label>
                <input value={formData.port} onChange={e => setFormData({...formData, port: e.target.value})} type="number" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Username *</label>
                <input value={formData.username} onChange={e => setFormData({...formData, username: e.target.value})} type="text" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Password *</label>
                <input value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} type="password" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Latitude</label>
                <input value={formData.lat} onChange={e => setFormData({...formData, lat: e.target.value})} type="number" step="any" className={inputCls} placeholder="-6.2088" />
              </div>
              <div>
                <label className={labelCls}>Longitude</label>
                <input value={formData.lng} onChange={e => setFormData({...formData, lng: e.target.value})} type="number" step="any" className={inputCls} placeholder="106.8456" />
              </div>
            </div>

            <button
              onClick={handleAdd}
              disabled={sites.length >= 2}
              className={`mt-4 w-full bg-gradient-to-r from-indigo-600 to-blue-600 text-white font-semibold py-2.5 rounded-xl flex items-center justify-center gap-2 transition ${sites.length >= 2 ? 'opacity-50 cursor-not-allowed' : 'hover:opacity-85 shadow'}`}
            >
              <Plus className="w-4 h-4" /> Tambah Site
            </button>
            {sites.length >= 2 && (
              <p className="mt-3 text-amber-400 text-xs text-center bg-amber-400/10 rounded-lg px-3 py-2">
                ⚠️ Batas maksimal 2 site telah tercapai.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
