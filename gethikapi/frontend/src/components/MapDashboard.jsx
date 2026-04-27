import { useState } from 'react'
import 'leaflet/dist/leaflet.css'
import { MapContainer, TileLayer, Marker } from 'react-leaflet'
import { divIcon } from 'leaflet'
import DeviceMonitorModal from './DeviceMonitorModal'

export default function MapDashboard({ sites }) {
  const [monitorSite, setMonitorSite] = useState(null)

  const makeSiteIcon = (alerting = false) => {
    const color = alerting ? '#ef4444' : '#3b82f6'
    return divIcon({
      className: 'custom-div-icon',
      html: `<div class="relative flex h-9 w-9 items-center justify-center">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60" style="background:${color}"></span>
          <span class="relative inline-flex rounded-full h-5 w-5 border-2 border-white shadow-lg" style="background:${color}"></span>
      </div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    })
  }

  return (
    <>
      <MapContainer center={[-6.2088, 106.8456]} zoom={13} className="absolute inset-0 z-10">
        <TileLayer
          attribution='&copy; OpenStreetMap contributors &copy; CARTO'
          url='https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'
        />
        
        {sites.map(site => (
          site.lat && site.lng ? (
            <Marker 
              key={site.id} 
              position={[site.lat, site.lng]} 
              icon={makeSiteIcon()}
              eventHandlers={{
                click: () => setMonitorSite(site)
              }}
            />
          ) : null
        ))}
      </MapContainer>

      {monitorSite && (
        <DeviceMonitorModal site={monitorSite} onClose={() => setMonitorSite(null)} />
      )}
    </>
  )
}
