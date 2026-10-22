import { useEffect, useRef } from 'react'
import { Map as MapLibreMap, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { telemetryFrames } from '../state/telemetryStore'
import { useTelemetryStore } from '../state/telemetryStore'

type LatLon = readonly [lat_deg: number, lon_deg: number]
type Area = readonly LatLon[]
type Coordinate = [number, number]
type Feature = {
  type: 'Feature'
  properties: Record<string, string | number>
  geometry:
    | { type: 'Point'; coordinates: Coordinate }
    | { type: 'LineString'; coordinates: Coordinate[] }
    | { type: 'Polygon'; coordinates: Coordinate[][] }
}
type Collection = { type: 'FeatureCollection'; features: Feature[] }

const HOME: LatLon = [31.634, 74.8723]
const emptyCollection = (): Collection => ({ type: 'FeatureCollection', features: [] })
const toFeatureCollection = (features: Feature[]): Collection => ({ type: 'FeatureCollection', features })

function makeGrid(center: LatLon): Collection {
  const features: Feature[] = []
  for (let offset = -10; offset <= 10; offset += 1) {
    const lat = center[0] + offset * 0.001
    const lon = center[1] + offset * 0.001
    features.push(
      { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [[center[1] - 0.01, lat], [center[1] + 0.01, lat]] } },
      { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [[lon, center[0] - 0.01], [lon, center[0] + 0.01]] } },
    )
  }
  return toFeatureCollection(features)
}

function polygonFeature(area: Area, kind: string): Feature {
  const ring = area.map(([lat, lon]) => [lon, lat] as Coordinate)
  if (ring.length > 0 && (ring[0][0] !== ring.at(-1)?.[0] || ring[0][1] !== ring.at(-1)?.[1])) {
    ring.push([...ring[0]])
  }
  return { type: 'Feature', properties: { kind }, geometry: { type: 'Polygon', coordinates: [ring] } }
}

const style: StyleSpecification = {
  version: 8,
  sources: {
    grid: { type: 'geojson', data: emptyCollection() },
    areas: { type: 'geojson', data: emptyCollection() },
    trail: { type: 'geojson', data: emptyCollection() },
    proposal: { type: 'geojson', data: emptyCollection() },
    vehicle: { type: 'geojson', data: emptyCollection() },
  },
  layers: [
    { id: 'ground', type: 'background', paint: { 'background-color': '#191e1b' } },
    { id: 'grid', type: 'line', source: 'grid', paint: { 'line-color': '#303a32', 'line-width': 1 } },
    { id: 'fence-fill', type: 'fill', source: 'areas', filter: ['==', ['get', 'kind'], 'geofence'], paint: { 'fill-color': '#a6d66b', 'fill-opacity': 0.07 } },
    { id: 'fence-line', type: 'line', source: 'areas', filter: ['==', ['get', 'kind'], 'geofence'], paint: { 'line-color': '#a6d66b', 'line-width': 2, 'line-dasharray': [2, 1] } },
    { id: 'no-fly-fill', type: 'fill', source: 'areas', filter: ['==', ['get', 'kind'], 'no-fly'], paint: { 'fill-color': '#ee766d', 'fill-opacity': 0.16 } },
    { id: 'no-fly-line', type: 'line', source: 'areas', filter: ['==', ['get', 'kind'], 'no-fly'], paint: { 'line-color': '#ee766d', 'line-width': 2 } },
    { id: 'trail', type: 'line', source: 'trail', paint: { 'line-color': '#72c6b8', 'line-width': 2, 'line-opacity': 0.8 } },
    { id: 'proposal-line', type: 'line', source: 'proposal', filter: ['==', ['get', 'kind'], 'path'], paint: { 'line-color': '#e8b354', 'line-width': 3, 'line-dasharray': [2, 1] } },
    { id: 'proposal-points', type: 'circle', source: 'proposal', filter: ['==', ['get', 'kind'], 'waypoint'], paint: { 'circle-radius': 4, 'circle-color': '#e8b354', 'circle-stroke-color': '#171a18', 'circle-stroke-width': 1 } },
    { id: 'heading', type: 'line', source: 'vehicle', filter: ['==', ['get', 'kind'], 'heading'], paint: { 'line-color': '#a6d66b', 'line-width': 3 } },
    { id: 'vehicle', type: 'circle', source: 'vehicle', filter: ['==', ['get', 'kind'], 'vehicle'], paint: { 'circle-radius': 6, 'circle-color': '#a6d66b', 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2 } },
  ],
}

export interface TacticalMapProps {
  geofence?: Area
  noFlyZones?: readonly Area[]
  sampleGeometry?: boolean
}

export function TacticalMap({ geofence = [], noFlyZones = [], sampleGeometry = false }: TacticalMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const vertices = [...geofence, ...noFlyZones.flat()]
    const initialCenter = vertices.length
      ? [
          (Math.min(...vertices.map(([lat]) => lat)) + Math.max(...vertices.map(([lat]) => lat))) / 2,
          (Math.min(...vertices.map(([, lon]) => lon)) + Math.max(...vertices.map(([, lon]) => lon))) / 2,
        ] as const
      : HOME
    const map = new MapLibreMap({
      container,
      style,
      center: [initialCenter[1], initialCenter[0]],
      zoom: 14.25,
      attributionControl: false,
      renderWorldCopies: false,
    })
    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(container)
    const trail: Coordinate[] = []
    let lastSeq = -1
    let lastProposalId = ''
    let animationFrame = 0
    let active = true

    map.once('load', () => {
      const setData = (id: string, data: Collection) => {
        const source = map.getSource(id)
        if (source && 'setData' in source && typeof source.setData === 'function') source.setData(data)
      }
      const areas = [
        ...(geofence.length > 0 ? [polygonFeature(geofence, 'geofence')] : []),
        ...noFlyZones.map((area) => polygonFeature(area, 'no-fly')),
      ]
      setData('grid', makeGrid(initialCenter))
      setData('areas', toFeatureCollection(areas))

      const render = () => {
        if (!active) return
        const position = telemetryFrames.position
        const receivedAt = telemetryFrames.positionReceivedAt
        const stale = receivedAt === null || performance.now() - receivedAt > 1000
        container.style.opacity = stale ? '0.35' : '1'

        if (position) {
          const { lat_deg, lon_deg, heading_deg } = position.data
          const vehicle: Coordinate = [lon_deg, lat_deg]
          const headingRad = (heading_deg * Math.PI) / 180
          const endpoint: Coordinate = [
            lon_deg + (Math.sin(headingRad) * 25) / (111320 * Math.cos((lat_deg * Math.PI) / 180)),
            lat_deg + (Math.cos(headingRad) * 25) / 111320,
          ]
          if (position.seq !== lastSeq) {
            if (lastSeq === -1 || !map.getBounds().contains(vehicle)) {
              map.easeTo({ center: vehicle, duration: 350 })
            }
            setData('vehicle', toFeatureCollection([
              { type: 'Feature', properties: { kind: 'vehicle' }, geometry: { type: 'Point', coordinates: vehicle } },
              { type: 'Feature', properties: { kind: 'heading' }, geometry: { type: 'LineString', coordinates: [vehicle, endpoint] } },
            ]))
            trail.push(vehicle)
            if (trail.length > 120) trail.shift()
            setData('trail', toFeatureCollection(trail.length > 1
              ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [...trail] } }]
              : []))
            lastSeq = position.seq
          }
        }
        const proposal = useTelemetryStore.getState().proposal
        if (proposal && proposal.proposal_id !== lastProposalId) {
          const points = proposal.waypoints
            .slice()
            .sort((a, b) => a.seq - b.seq)
            .map((waypoint): Coordinate => [waypoint.lon_deg, waypoint.lat_deg])
          const features: Feature[] = points.map((coordinates, index) => ({
            type: 'Feature',
            properties: { kind: 'waypoint', seq: index + 1 },
            geometry: { type: 'Point', coordinates },
          }))
          if (points.length > 1) {
            features.push({
              type: 'Feature',
              properties: { kind: 'path' },
              geometry: { type: 'LineString', coordinates: points },
            })
          }
          setData('proposal', toFeatureCollection(features))
          lastProposalId = proposal.proposal_id
        }
        animationFrame = window.requestAnimationFrame(render)
      }
      render()
    })

    return () => {
      active = false
      window.cancelAnimationFrame(animationFrame)
      resizeObserver.disconnect()
      map.remove()
    }
  }, [geofence, noFlyZones])

  return (
    <div className={`tactical-map${sampleGeometry ? ' tactical-map--sample' : ''}`}>
      <div className="tactical-map__canvas" ref={containerRef} aria-label="Tactical map with vehicle, trail and airspace overlays" />
      <div className="tactical-map__legend" aria-label="Map legend">
        <span><i className="legend-vehicle" />VEHICLE / TRAIL</span>
        {geofence.length > 0 && <span><i className="legend-geofence" />GEOFENCE</span>}
        {noFlyZones.length > 0 && <span><i className="legend-no-fly" />NO-FLY</span>}
        {sampleGeometry && <b>SAMPLE GEOMETRY</b>}
      </div>
    </div>
  )
}
