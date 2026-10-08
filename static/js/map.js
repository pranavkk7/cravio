// Restaurant map: Leaflet with OpenStreetMap tiles (free, no API key). Built the first time the
// map panel is opened, because Leaflet cannot measure a hidden element.
const panel = document.querySelector('[data-map-panel]')
const dataElement = document.getElementById('map-data')

if (panel && dataElement && window.L) {
  const data = JSON.parse(dataElement.textContent)
  let map = null

  const escape = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

  const build = () => {
    map = L.map(panel.querySelector('.map'), { scrollWheelZoom: false })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)

    const points = []
    data.restaurants.forEach((r) => {
      const far = data.me && !r.inRange
      L.circleMarker([r.lat, r.lng], {
        radius: 9, weight: 3, color: '#fff', fillOpacity: 1, fillColor: far ? '#9b8790' : '#d4243f',
      })
        .addTo(map)
        .bindPopup(`<a href="${r.url}"><b>${escape(r.name)}</b></a><br>${escape(r.area)}${far ? '<br><i>Out of delivery range</i>' : ''}`)
      points.push([r.lat, r.lng])
    })

    if (data.me) {
      L.circleMarker([data.me.lat, data.me.lng], {
        radius: 10, weight: 4, color: '#fff', fillOpacity: 1, fillColor: '#2563eb',
      }).addTo(map).bindPopup(`<b>You</b><br>${escape(data.me.label)}`)
      points.push([data.me.lat, data.me.lng])
    }

    if (points.length) map.fitBounds(points, { padding: [36, 36], maxZoom: 14 })
    else map.setView([12.4, 76.6], 7) // all three cities in view
  }

  panel.addEventListener('toggle', () => {
    if (!panel.open) return
    if (map) map.invalidateSize()
    else build()
  })
  if (panel.open) build()
}
