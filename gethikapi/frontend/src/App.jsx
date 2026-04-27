import { useState, useEffect } from 'react'
import { HashRouter as Router, Routes, Route, useNavigate } from 'react-router-dom'
import { Activity, Bell, Settings, FileText } from 'lucide-react'
import MapDashboard from './components/MapDashboard'
import NotificationSidebar from './components/NotificationSidebar'
import SiteModal from './components/SiteModal'
import HistoryDetail from './pages/HistoryDetail'

function DashboardLayout({ sites, loadSites }) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isSiteModalOpen, setIsSiteModalOpen] = useState(false)
  const navigate = useNavigate()

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gray-50">
      {/* HEADER */}
      <header className="glass-panel shadow-sm py-4 h-[80px] flex items-center justify-between px-6 z-50 relative border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl p-2">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600 tracking-tight">
            Network Management System View
          </h1>
        </div>

        <div className="flex items-center gap-2">


          <button 
            onClick={() => setIsSiteModalOpen(true)}
            className="flex items-center gap-2 bg-gradient-to-r from-slate-700 to-slate-800 text-white text-sm font-semibold px-4 py-2 rounded-xl hover:opacity-85 transition shadow"
          >
            <Settings className="h-4 w-4" />
            Kelola Site
          </button>

          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="flex items-center gap-2 bg-gradient-to-r from-indigo-600 to-blue-600 text-white text-sm font-semibold px-4 py-2 rounded-xl hover:opacity-85 transition shadow"
          >
            <Bell className="h-4 w-4" />
            Notifikasi
          </button>
        </div>
      </header>

      {/* MAP */}
      <main className="flex-grow relative overflow-hidden">
        <MapDashboard sites={sites} />
        
        {/* SIDEBAR */}
        <NotificationSidebar 
          isOpen={isSidebarOpen} 
          onClose={() => setIsSidebarOpen(false)} 
        />
      </main>

      {/* MODALS */}
      <SiteModal 
        isOpen={isSiteModalOpen} 
        onClose={() => setIsSiteModalOpen(false)} 
        sites={sites}
        reloadSites={loadSites}
      />
    </div>
  )
}

function HistoryPageWrapper() {
  const navigate = useNavigate()
  return <HistoryDetail onBack={() => navigate('/')} />
}

function App() {
  const [sites, setSites] = useState([])

  const loadSites = async () => {
    try {
      const res = await fetch('/sites/')
      const data = await res.json()
      setSites(data.sites || [])
    } catch (e) {
      console.error('Failed to load sites:', e)
    }
  }

  useEffect(() => {
    loadSites()
  }, [])

  return (
    <Router>
      <Routes>
        <Route path="/" element={<DashboardLayout sites={sites} loadSites={loadSites} />} />
        <Route path="/history" element={<HistoryPageWrapper />} />
      </Routes>
    </Router>
  )
}

export default App

