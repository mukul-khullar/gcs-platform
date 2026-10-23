import { useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentRef, RefObject } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Grid, Line, OrbitControls } from '@react-three/drei'
import type { Group, Vector3, Vector3Tuple } from 'three'
import { telemetryFrames, useTelemetryStore } from '../state/telemetryStore'
import type { PositionSample } from '../state/telemetryHistory'
import { toLocalNed } from './liveSceneMath'

type OrbitControlInstance = ComponentRef<typeof OrbitControls>

function LiveVehicle({ controlsRef }: { controlsRef: RefObject<OrbitControlInstance | null> }) {
  const vehicleRef = useRef<Group>(null)
  const lastPosition = useRef<Vector3 | null>(null)
  useFrame(() => {
    const vehicle = vehicleRef.current
    const position = telemetryFrames.position
    if (!vehicle || !position) {
      if (vehicle) vehicle.visible = false
      return
    }
    const positionAgeMs = telemetryFrames.positionReceivedAt === null
      ? Infinity
      : performance.now() - telemetryFrames.positionReceivedAt
    if (positionAgeMs > 1000) {
      vehicle.visible = false
      return
    }
    const attitudeFresh = telemetryFrames.attitudeReceivedAt !== null &&
      performance.now() - telemetryFrames.attitudeReceivedAt <= 1000
    const attitude = attitudeFresh ? telemetryFrames.attitude?.data : undefined
    const origin = telemetryFrames.positionHistory[0]
    const local = origin
      ? toLocalNed(position.data.lat_deg, position.data.lon_deg, origin.lat_deg, origin.lon_deg)
      : { north_m: 0, east_m: 0 }
    vehicle.visible = true
    vehicle.position.set(local.east_m, position.data.alt_rel_m, -local.north_m)
    vehicle.rotation.set(
      attitude?.pitch_rad ?? 0,
      -(position.data.heading_deg * Math.PI / 180),
      -(attitude?.roll_rad ?? 0),
    )
    const controls = controlsRef.current
    if (controls) {
      const currentPosition = vehicle.position.clone()
      const shift = lastPosition.current
        ? currentPosition.clone().sub(lastPosition.current)
        : currentPosition.clone().sub(controls.target)
      controls.target.add(shift)
      controls.object.position.add(shift)
      controls.update()
      lastPosition.current = currentPosition
    }
  })

  return (
    <group ref={vehicleRef} visible={false}>
      <mesh><boxGeometry args={[2.2, 0.4, 1.5]} /><meshStandardMaterial color="#55595c" metalness={0.1} roughness={0.8} /></mesh>
      {[-1, 1].flatMap((x) => [-1, 1].map((z) => (
        <mesh key={`${x}:${z}`} position={[x * 0.85, 0, z * 0.62]}>
          <boxGeometry args={[1.7, 0.1, 0.12]} /><meshStandardMaterial color="#bfc2c4" />
        </mesh>
      )))}
      <mesh position={[0, 0, -0.95]}><coneGeometry args={[0.24, 0.55, 3]} /><meshStandardMaterial color="#777c80" /></mesh>
    </group>
  )
}

export function LiveFlightPreview() {
  const proposal = useTelemetryStore((state) => state.proposal)
  const controlsRef = useRef<OrbitControlInstance>(null)
  const [trail, setTrail] = useState<Vector3Tuple[]>([])
  const [mapOrigin, setMapOrigin] = useState<PositionSample | null>(null)
  const [freshness, setFreshness] = useState<'WAITING' | 'LIVE' | 'STALE'>('WAITING')

  useEffect(() => {
    const timer = window.setInterval(() => {
      const { position, positionHistory, positionReceivedAt } = telemetryFrames
      const ageMs = positionReceivedAt === null ? Infinity : performance.now() - positionReceivedAt
      setFreshness(position === null ? 'WAITING' : ageMs > 1000 ? 'STALE' : 'LIVE')
      if (positionHistory.length < 2) {
        setTrail([])
        setMapOrigin(positionHistory[0] ?? null)
        return
      }
      const origin = positionHistory[0]
      setMapOrigin(origin)
      setTrail(positionHistory.slice(-180).map((sample) => {
        const local = toLocalNed(sample.lat_deg, sample.lon_deg, origin.lat_deg, origin.lon_deg)
        return [local.east_m, sample.alt_rel_m, -local.north_m]
      }))
    }, 250)
    return () => window.clearInterval(timer)
  }, [])

  const route = useMemo(() => {
    const origin = mapOrigin
    if (!origin || !proposal) return []
    return proposal.waypoints
      .slice()
      .sort((a, b) => a.seq - b.seq)
      .map((waypoint): Vector3Tuple => {
        const local = toLocalNed(waypoint.lat_deg, waypoint.lon_deg, origin.lat_deg, origin.lon_deg)
        return [local.east_m, waypoint.alt_rel_m, -local.north_m]
      })
  }, [proposal, mapOrigin])

  return (
    <section className="panel live-flight-panel" aria-label="Live three-dimensional flight view">
      <div className="panel-heading">
        <div><p className="eyebrow">POSITION · ATTITUDE · RELATIVE ALTITUDE</p><h2>Live 3D flight view</h2></div>
        <span className={`flight-feed flight-feed--${freshness.toLowerCase()}`}>{freshness === 'LIVE' ? 'LIVE TELEMETRY' : freshness === 'STALE' ? 'STALE TELEMETRY' : 'NO POSITION DATA'}</span>
      </div>
      <div className="live-flight-canvas">
        <Canvas camera={{ position: [26, 78, 26], fov: 48, near: 0.1, far: 1000 }} dpr={[1, 1.25]}>
          <color attach="background" args={['#f1f2f2']} />
          <ambientLight intensity={1.2} />
          <directionalLight position={[24, 40, 12]} intensity={1.7} />
          <Grid args={[300, 300]} cellSize={5} cellThickness={0.5} cellColor="#d7d9da" sectionSize={25} sectionThickness={1} sectionColor="#a5a9ab" fadeDistance={250} infiniteGrid />
          {trail.length > 1 && <Line points={trail} color="#656a6d" lineWidth={2} />}
          {route.length > 1 && <Line points={route} color="#d28a18" lineWidth={2} dashed dashSize={2} gapSize={1.5} />}
          {route.map((point, index) => <mesh key={`route-${index}`} position={point}><sphereGeometry args={[0.6, 12, 8]} /><meshStandardMaterial color="#d28a18" /></mesh>)}
          <LiveVehicle controlsRef={controlsRef} />
          <OrbitControls ref={controlsRef} makeDefault target={[0, 50, 0]} minDistance={8} maxDistance={240} />
        </Canvas>
        <span className="live-flight-label">LOCAL NED · 1 GRID = 5 m</span>
        <span className="live-flight-north" aria-label="North">N ↑</span>
      </div>
      <div className="flight-legend"><span><i className="flight-legend__vehicle" /> AIRCRAFT</span><span><i className="flight-legend__trail" /> OBSERVED TRAIL</span><span><i className="flight-legend__route" /> PROPOSAL ROUTE</span></div>
      <p className="live-flight-note">Aircraft position and attitude come from the validated telemetry feed. Route appears only when a planner proposal is available. The local view does not issue commands.</p>
    </section>
  )
}
