import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Grid, Line, OrbitControls } from '@react-three/drei'
import type { Group } from 'three'
import {
  DEFAULT_ROUTE,
  advanceSimulation,
  initialSimulationState,
  nedToThree,
  pauseSimulation,
  startSimulation,
} from './simulation'
import type { SimulationState } from './simulation'

type CameraMode = 'orbit' | 'top' | 'side' | 'chase'

function VehicleModel({
  stateRef,
  vehicleRef,
}: {
  stateRef: RefObject<SimulationState>
  vehicleRef: RefObject<Group | null>
}) {
  useFrame(() => {
    if (!vehicleRef.current) return
    const state = stateRef.current
    const position = nedToThree(state.position_ned_m)
    vehicleRef.current.position.set(...position)
    vehicleRef.current.rotation.set(
      state.attitude_rad.pitch_rad,
      -state.attitude_rad.yaw_rad,
      -state.attitude_rad.roll_rad,
    )
  })

  return (
    <group ref={vehicleRef}>
      <mesh castShadow>
        <boxGeometry args={[1.8, 0.38, 1.3]} />
        <meshStandardMaterial color="#55595c" metalness={0.1} roughness={0.8} />
      </mesh>
      {[-1, 1].flatMap((x) => [-1, 1].map((z) => (
        <group key={`${x}:${z}`} position={[x * 0.8, 0, z * 0.62]}>
          <mesh rotation={[0, Math.PI / 4 * x * z, 0]} castShadow>
            <boxGeometry args={[1.7, 0.12, 0.16]} />
            <meshStandardMaterial color="#c2c5c6" metalness={0.1} roughness={0.8} />
          </mesh>
          <mesh position={[0, 0.1, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
            <cylinderGeometry args={[0.48, 0.48, 0.08, 20]} />
            <meshStandardMaterial color="#8e9396" transparent opacity={0.55} />
          </mesh>
          <mesh position={[0, 0.22, 0]}>
            <sphereGeometry args={[0.1, 12, 8]} />
            <meshStandardMaterial color="#d28a18" />
          </mesh>
        </group>
      )))}
      <mesh position={[0, 0, -0.72]}>
        <coneGeometry args={[0.23, 0.55, 3]} />
        <meshStandardMaterial color="#c73535" />
      </mesh>
    </group>
  )
}

function CameraRig({ mode, revision, vehicleRef }: { mode: CameraMode; revision: number; vehicleRef: RefObject<Group | null> }) {
  const { camera } = useThree()
  useEffect(() => {
    if (mode === 'chase') return
    camera.up.set(0, 1, 0)
    if (mode === 'top') {
      camera.position.set(0, 74, 0.01)
      camera.up.set(0, 0, -1)
    } else if (mode === 'side') {
      camera.position.set(62, 25, 0)
    } else {
      camera.position.set(33, 28, 36)
    }
    camera.lookAt(0, 8, 0)
  }, [camera, mode, revision])

  useFrame(() => {
    if (mode !== 'chase' || !vehicleRef.current) return
    const vehicle = vehicleRef.current
    const yaw = vehicle.rotation.y
    camera.position.set(
      vehicle.position.x + Math.sin(yaw) * 16,
      vehicle.position.y + 8,
      vehicle.position.z + Math.cos(yaw) * 16,
    )
    camera.lookAt(vehicle.position)
  })
  return null
}

function Scene({ state, stateRef, cameraMode, cameraRevision }: {
  state: SimulationState
  stateRef: RefObject<SimulationState>
  cameraMode: CameraMode
  cameraRevision: number
}) {
  const vehicleRef = useRef<Group>(null)
  const routePoints = DEFAULT_ROUTE.map((point) => nedToThree({
    north_m: point.north_m,
    east_m: point.east_m,
    down_m: -point.alt_rel_m,
  }))
  const trailPoints = state.trail_ned_m.map(nedToThree)

  return (
    <>
      <color attach="background" args={['#f1f2f2']} />
      <ambientLight intensity={1.35} />
      <directionalLight position={[18, 35, 12]} intensity={2.1} castShadow />
      <Grid
        args={[120, 120]}
        cellSize={2}
        cellThickness={0.55}
        cellColor="#d7d9da"
        sectionSize={10}
        sectionThickness={1}
        sectionColor="#9da1a3"
        fadeDistance={100}
        infiniteGrid
      />
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.32, 16, 12]} />
        <meshStandardMaterial color="#55595c" />
      </mesh>
      <Line points={routePoints} color="#d28a18" lineWidth={1.5} dashed dashSize={1.2} gapSize={0.7} />
      {routePoints.map((point, index) => (
        <mesh key={`waypoint-${index}`} position={point}>
          <sphereGeometry args={[0.42, 16, 12]} />
          <meshStandardMaterial color="#d28a18" />
        </mesh>
      ))}
      {trailPoints.length > 1 && (
        <Line points={trailPoints} color="#656a6d" lineWidth={2.5} />
      )}
      <VehicleModel stateRef={stateRef} vehicleRef={vehicleRef} />
      <CameraRig mode={cameraMode} revision={cameraRevision} vehicleRef={vehicleRef} />
      <OrbitControls makeDefault enabled={cameraMode === 'orbit'} target={[0, 8, 0]} />
    </>
  )
}

function angleDegrees(angle_rad: number): string {
  return `${(angle_rad * 180 / Math.PI).toFixed(1)}°`
}

export function SimulatorView() {
  const [state, setState] = useState(initialSimulationState)
  const stateRef = useRef(state)
  const [cameraMode, setCameraMode] = useState<CameraMode>('orbit')
  const [cameraRevision, setCameraRevision] = useState(0)

  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    if (!state.running) return
    let frame = 0
    let previousTime: number | null = null
    let lastPublishTime = 0
    const tick = (now: number) => {
      const delta_s = previousTime === null ? 0 : Math.min((now - previousTime) / 1000, 0.1)
      previousTime = now
      if (delta_s > 0) {
        const next = advanceSimulation(stateRef.current, delta_s)
        stateRef.current = next
        if (now - lastPublishTime >= 80 || !next.running) {
          setState(next)
          lastPublishTime = now
        }
      }
      if (stateRef.current.running) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [state.running])

  const changeState = (update: (current: SimulationState) => SimulationState) => {
    const next = update(stateRef.current)
    stateRef.current = next
    setState(next)
  }
  const hasProgress = state.elapsed_s > 0
  const runLabel = state.running
    ? 'SIMULATION RUNNING'
    : state.complete
      ? 'SIMULATION COMPLETE'
      : hasProgress
        ? 'SIMULATION PAUSED'
        : 'SIMULATION READY'

  return (
    <section className="simulator-view" aria-labelledby="simulator-title">
      <div className="simulator-heading">
        <div>
          <p className="eyebrow">LOCAL FLIGHT DYNAMICS · ADVISORY ONLY</p>
          <h2 id="simulator-title">3D mission simulator</h2>
        </div>
      </div>
      <div className="simulator-toolbar">
        <div className="simulator-transport" aria-label="Simulator controls">
          <button
            type="button"
            className="simulator-button simulator-button--primary"
            onClick={() => changeState((current) => startSimulation(
              current.complete ? initialSimulationState() : current,
            ))}
            disabled={state.running}
          >
            {state.complete ? 'RESTART' : hasProgress ? 'RESUME' : 'START'}
          </button>
          <button
            type="button"
            className="simulator-button"
            onClick={() => changeState(pauseSimulation)}
            disabled={!state.running}
          >
            PAUSE
          </button>
          <button
            type="button"
            className="simulator-button"
            onClick={() => changeState(initialSimulationState)}
          >
            RESET
          </button>
        </div>
        <span className={`simulator-run-state${state.running ? ' simulator-run-state--active' : ''}`}>
          <span aria-hidden="true">{state.running ? '▶' : '■'}</span>{runLabel}
        </span>
        <div className="camera-controls" aria-label="Camera view">
          {([
            ['orbit', 'ORBIT'],
            ['top', 'TOP'],
            ['side', 'SIDE'],
            ['chase', 'CHASE'],
          ] as const).map(([mode, label]) => (
            <button
              type="button"
              key={mode}
              aria-pressed={cameraMode === mode}
              onClick={() => {
                setCameraMode(mode)
                setCameraRevision((revision) => revision + 1)
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="simulator-canvas" aria-label="Interactive 3D vehicle simulation">
        <Canvas
          camera={{ position: [33, 28, 36], fov: 45, near: 0.1, far: 500 }}
          dpr={[1, 1.5]}
        >
          <Scene state={state} stateRef={stateRef} cameraMode={cameraMode} cameraRevision={cameraRevision} />
        </Canvas>
        <div className="simulator-canvas-label">LOCAL NED · GRID 2 m · PLANNED ROUTE</div>
        <div className="simulator-canvas-compass" aria-hidden="true">N ↑</div>
      </div>
      <div className="simulator-hud" aria-label="Simulated telemetry">
        <div><span>ALTITUDE</span><strong>{state.position_ned_m.down_m < 0 ? `${(-state.position_ned_m.down_m).toFixed(1)} m` : '0.0 m'}</strong></div>
        <div><span>GROUND SPEED</span><strong>{state.speed_mps.toFixed(1)} m/s</strong></div>
        <div><span>HEADING</span><strong>{state.heading_deg.toFixed(0)}°</strong></div>
        <div><span>ROLL</span><strong>{angleDegrees(state.attitude_rad.roll_rad)}</strong></div>
        <div><span>PITCH</span><strong>{angleDegrees(state.attitude_rad.pitch_rad)}</strong></div>
        <div><span>WAYPOINT</span><strong>{String(state.waypoint_index + 1).padStart(2, '0')} / {DEFAULT_ROUTE.length}</strong></div>
        <div><span>BATTERY · SIMULATED</span><strong>{state.battery_pct.toFixed(1)}%</strong></div>
        <div><span>ELAPSED</span><strong>{state.elapsed_s.toFixed(1)} s</strong></div>
      </div>
      <p className="simulator-disclaimer">
        Deterministic local simulation. Synthetic position, attitude and battery values are not vehicle telemetry.
        Live-link status is shown separately and is never replaced by this simulation.
      </p>
    </section>
  )
}
