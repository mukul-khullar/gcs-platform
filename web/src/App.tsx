import { useEffect, useState } from 'react'
import { connectTelemetry, telemetryWebSocketUrl } from './state/telemetryClient'
import { useTelemetryStore } from './state/telemetryStore'
import { Pfd } from './instruments/Pfd'
import { FlightHistoryPanel } from './instruments/FlightHistoryPanel'
import { TacticalMap } from './map/TacticalMap'
import { SystemsPanel } from './panels/SystemsPanel'
import { CommandBar } from './panels/CommandBar'
import { PlanPanel } from './panels/PlanPanel'
import { AuditPanel } from './panels/AuditPanel'
import { SimulatorView } from './simulator/SimulatorView'
import { LiveFlightPreview } from './simulator/LiveFlightPreview'
import { telemetryFrames } from './state/telemetryStore'
import type { LinkState } from './state/telemetryStore'

type ViewId =
  | 'dashboard'
  | 'simulator'
  | 'planner'
  | 'telemetry'
  | 'health'
  | 'control'
  | 'replay'
  | 'events'
  | 'audit'
  | 'settings'

const navigation: { id: ViewId; label: string; icon: string; group: string }[] = [
  { id: 'dashboard', label: 'Overview', icon: '▦', group: 'OVERVIEW' },
  { id: 'simulator', label: '3D Flight view', icon: '◇', group: 'OVERVIEW' },
  { id: 'planner', label: 'Mission planner', icon: '⌖', group: 'OVERVIEW' },
  { id: 'telemetry', label: 'Live telemetry', icon: '⌁', group: 'AIRCRAFT' },
  { id: 'health', label: 'Vehicle health', icon: '✳', group: 'AIRCRAFT' },
  { id: 'control', label: 'Flight control', icon: '⊕', group: 'AIRCRAFT' },
  { id: 'events', label: 'Anomaly events', icon: '!', group: 'REVIEW' },
  { id: 'replay', label: 'Flight recorder / replay', icon: '↺', group: 'REVIEW' },
  { id: 'audit', label: 'Action audit', icon: '≡', group: 'REVIEW' },
  { id: 'settings', label: 'Settings', icon: '⚙', group: 'SYSTEM' },
]

const validViews = new Set<ViewId>(navigation.map(({ id }) => id))
const isDefaultMockLink = !import.meta.env.VITE_TELEMETRY_WS_URL

function viewFromHash(): ViewId {
  const view = window.location.hash.slice(1) as ViewId
  return validViews.has(view) ? view : 'dashboard'
}

function StatusLamp({ state, label }: { state: string; label: string }) {
  return (
    <span className={`status-lamp status-lamp--${state}`}>
      <span className="status-lamp__icon" aria-hidden="true">{state === 'online' ? '✓' : state === 'offline' ? '×' : '!'}</span>
      <span>{label}</span>
    </span>
  )
}

function connectionPresentation(linkState: LinkState) {
  if (linkState === 'connected') return { state: 'online', label: 'CONNECTED' }
  if (linkState === 'connecting') return { state: 'caution', label: 'CONNECTING' }
  if (linkState === 'reconnecting') return { state: 'caution', label: 'RECONNECTING' }
  return { state: 'offline', label: 'DISCONNECTED' }
}

function utcTimeLabel(timeMs: number): string {
  const date = new Date(timeMs)
  return Number.isNaN(date.valueOf()) ? `t_wall_ms=${timeMs}` : `${date.toISOString().slice(11, 19)}Z`
}

function TelemetryMetrics() {
  const [nowMs, setNowMs] = useState(0)
  const subsystems = useTelemetryStore((state) => state.subsystems)
  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(performance.now()), 250)
    return () => window.clearInterval(interval)
  }, [])

  const position = telemetryFrames.position?.data
  const attitude = telemetryFrames.attitude?.data
  const positionAge = telemetryFrames.positionReceivedAt === null
    ? null
    : Math.max(0, (nowMs - telemetryFrames.positionReceivedAt) / 1000)
  const attitudeAge = telemetryFrames.attitudeReceivedAt === null
    ? null
    : Math.max(0, (nowMs - telemetryFrames.attitudeReceivedAt) / 1000)
  const velocity = position?.vel_ned_mps
  const speed = velocity ? Math.hypot(velocity[0], velocity[1]) : null
  const degrees = (angle_rad: number | undefined) => angle_rad === undefined
    ? '—'
    : `${(angle_rad * 180 / Math.PI).toFixed(1)}°`
  const positionAgeLabel = positionAge === null ? 'NO DATA' : positionAge > 1 ? 'STALE' : `${positionAge.toFixed(1)} s ago`
  const attitudeAgeLabel = attitudeAge === null ? 'NO DATA' : attitudeAge > 1 ? 'STALE' : `${attitudeAge.toFixed(1)} s ago`
  const metrics = [
    { label: 'ALTITUDE · REL', value: position ? `${position.alt_rel_m.toFixed(1)} m` : '—', stale: positionAge === null || positionAge > 1, ageLabel: positionAgeLabel },
    { label: 'GROUND SPEED', value: speed === null ? '—' : `${speed.toFixed(1)} m/s`, stale: positionAge === null || positionAge > 1, ageLabel: positionAgeLabel },
    { label: 'HEADING', value: position ? `${position.heading_deg.toFixed(1)}°` : '—', stale: positionAge === null || positionAge > 1, ageLabel: positionAgeLabel },
    { label: 'ROLL / PITCH', value: attitude ? `${degrees(attitude.roll_rad)} / ${degrees(attitude.pitch_rad)}` : '—', stale: attitudeAge === null || attitudeAge > 1, ageLabel: attitudeAgeLabel },
    { label: 'BATTERY HEALTH', value: subsystems.batt?.state ?? '—', stale: !subsystems.batt, ageLabel: subsystems.batt ? 'HEALTH SUMMARY' : 'NO DATA' },
    { label: 'GPS STATUS', value: subsystems.gps?.state ?? '—', stale: !subsystems.gps, ageLabel: subsystems.gps ? 'HEALTH SUMMARY' : 'NO DATA' },
  ]

  return (
    <div className="metric-grid" aria-label="Telemetry snapshot">
      {metrics.map(({ label, value, stale, ageLabel }) => (
        <div className={`metric-card${stale ? ' metric-card--stale' : ''}`} key={label}>
          <span className="metric-card__label">{label}</span>
          <strong className="metric-card__value">{value}</strong>
          <span className="metric-card__age">{ageLabel}</span>
        </div>
      ))}
    </div>
  )
}

function CwsPanel() {
  const cwsItems = useTelemetryStore((state) => state.cwsItems)
  const acknowledge = useTelemetryStore((state) => state.acknowledgeCwsItem)
  const acknowledgeAll = useTelemetryStore((state) => state.acknowledgeAllCwsItems)
  const logAudit = useTelemetryStore((state) => state.logAudit)
  const protocolError = useTelemetryStore((state) => state.protocolError)
  const unacknowledged = cwsItems.filter((item) => !item.acknowledged)
  const severityRank = { CAUTION: 1, WARNING: 2, CRITICAL: 3 } as const
  const masterSeverity = unacknowledged.reduce<keyof typeof severityRank>(
    (highest, item) => severityRank[item.severity] > severityRank[highest] ? item.severity : highest,
    'CAUTION',
  )
  const active = cwsItems.filter((item) => item.active && !item.acknowledged)
  const acknowledgeOne = (id: string, title: string) => {
    acknowledge(id)
    logAudit('CWS · ACKNOWLEDGE', 'INFO', `Operator acknowledged ${title}`)
  }
  return (
    <section className="panel cws-panel" aria-labelledby="cws-title">
      <div className="panel-heading">
        <div><p className="eyebrow">CREW WARNING SYSTEM</p><h2 id="cws-title">Active annunciators</h2></div>
        <span className={`count-badge${active.length ? ' count-badge--alert' : ''}`}>{active.length.toString().padStart(2, '0')}</span>
      </div>
      <div className={`master-alarm master-alarm--${unacknowledged.length ? masterSeverity.toLowerCase() : 'clear'}`} role={unacknowledged.length ? 'alert' : 'status'} aria-live="polite">
        <div>
          <strong>{unacknowledged.length ? `MASTER ${masterSeverity}` : 'MASTER ALARM CLEAR'}</strong>
          <span>{unacknowledged.length ? `${unacknowledged.length} annunciator${unacknowledged.length === 1 ? '' : 's'} require acknowledgement` : 'No unacknowledged annunciators'}</span>
        </div>
        <button
          type="button"
          className="acknowledge-button"
          onClick={() => {
            acknowledgeAll()
            logAudit('CWS · ACKNOWLEDGE', 'INFO', 'Operator acknowledged all latched annunciators')
          }}
          disabled={unacknowledged.length === 0}
        >
          ACKNOWLEDGE
        </button>
      </div>
      {protocolError && <div className="protocol-error" role="alert">{protocolError}</div>}
      {cwsItems.length === 0 ? (
        <p className="empty-state">No active advisories</p>
      ) : (
        <ul className="cws-list">
          {cwsItems.map((item) => (
            <li className={`cws-item cws-item--${item.severity.toLowerCase()}`} key={item.id}>
              <span className="cws-item__marker" aria-hidden="true">{item.severity === 'CRITICAL' || item.severity === 'WARNING' ? '!' : '▲'}</span>
              <span className="cws-item__text"><strong>{item.title}</strong><small>{item.detail}</small></span>
              {!item.acknowledged && <button type="button" className="text-button" onClick={() => acknowledgeOne(item.id, item.title)}>ACK</button>}
              {item.acknowledged && <span className="ack-label">{item.active ? 'ACKNOWLEDGED' : 'CLEARED · ACKNOWLEDGED'}</span>}
              {!item.active && !item.acknowledged && <span className="ack-label">CLEARED · ACK REQUIRED</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function OverviewView() {
  const health = useTelemetryStore((state) => state.health)
  const armed = useTelemetryStore((state) => state.armed)
  const mode = useTelemetryStore((state) => state.mode)
  const missionSeq = useTelemetryStore((state) => state.missionSeq)
  const proposal = useTelemetryStore((state) => state.proposal)
  const linkState = useTelemetryStore((state) => state.linkState)
  return (
    <>
      <div className="page-intro">
        <div><h1>Overview</h1></div>
        <div className="vehicle-state">
          <span><small>MODE</small><strong>{mode ?? '—'}</strong></span>
          <span><small>ARMED</small><strong className={armed ? 'text-warning' : ''}>{armed === null ? 'UNKNOWN' : armed ? 'YES' : 'NO'}</strong></span>
          <span><small>MISSION</small><strong>{proposal?.proposal_id ?? (missionSeq !== null ? `SEQ ${String(missionSeq).padStart(2, '0')}` : 'NO ACTIVE PLAN')}</strong></span>
        </div>
      </div>
      <TelemetryMetrics />
      <div className="dashboard-grid">
        <div className="dashboard-grid__main"><LiveFlightPreview /></div>
        <div className="dashboard-grid__side"><TacticalMap /><SystemsPanel /></div>
      </div>
      <div className="dashboard-grid dashboard-grid--lower">
        <CwsPanel />
        <section className="panel link-panel">
          <div className="panel-heading"><div><p className="eyebrow">AIRCRAFT LINK</p><h2>Connection status</h2></div><StatusLamp {...connectionPresentation(linkState)} /></div>
          <p className="link-panel__summary">{health ? `Overall vehicle health: ${health}` : 'Waiting for vehicle health report.'}</p>
          <p className="muted-copy">Connection loss is shown explicitly; no local telemetry is substituted.</p>
        </section>
      </div>
    </>
  )
}

function LiveTelemetryView() {
  return (
    <>
      <div className="page-intro"><div><p className="eyebrow">AIRCRAFT / LIVE TELEMETRY</p><h1>Flight instruments</h1><p>High-rate instrument and position display. Values dim when the feed is stale.</p></div></div>
      <TelemetryMetrics />
      <FlightHistoryPanel />
      <div className="dashboard-grid"><div className="dashboard-grid__main"><Pfd /></div><div className="dashboard-grid__side"><TacticalMap /></div></div>
    </>
  )
}

function VehicleHealthView() {
  return (
    <>
      <div className="page-intro"><div><p className="eyebrow">AIRCRAFT / VEHICLE HEALTH</p><h1>Systems & warnings</h1><p>Health telemetry, annunciators, and acknowledgement state.</p></div></div>
      <div className="health-layout"><SystemsPanel /><CwsPanel /></div>
    </>
  )
}

function PlannerView() {
  return (
    <>
      <div className="page-intro"><div><p className="eyebrow">PLANNING / MISSION PLANNER</p><h1>Route planning</h1><p>Review generated proposals and their constraint checks before approval.</p></div></div>
      <div className="planner-layout"><div className="planner-layout__map"><TacticalMap /></div><PlanPanel /></div>
    </>
  )
}

function FlightControlView() {
  return (
    <>
      <div className="page-intro"><div><p className="eyebrow">AIRCRAFT / FLIGHT CONTROL</p><h1>Confirmed commands</h1><p>Commands require preparation and explicit confirmation. No raw MAVLink passthrough.</p></div></div>
      <CommandBar />
      <div className="safety-note"><strong>CONTROL SAFETY</strong><p>Actions are allow-listed and confirmation-gated. Review the command preview before sliding to confirm.</p></div>
    </>
  )
}

function NotImplementedView({ title, description, status = 'FEATURE NOT IMPLEMENTED · NO PLACEHOLDER DATA' }: {
  title: string
  description: string
  status?: string
}) {
  return (
    <section className="panel unavailable-panel">
      <span className="unavailable-icon" aria-hidden="true">◌</span>
      <p className="eyebrow">NOT AVAILABLE IN THIS BUILD</p>
      <h2>{title}</h2>
      <p>{description}</p>
      <span className="implementation-state">{status}</span>
    </section>
  )
}

function AnomalyEventsView() {
  const items = useTelemetryStore((state) => state.cwsItems)
  const [severity, setSeverity] = useState('ALL')
  const [source, setSource] = useState('ALL')
  const [nowMs, setNowMs] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(performance.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const filtered = items.filter((item) =>
    (severity === 'ALL' || item.severity === severity) &&
    (source === 'ALL' || item.source === source),
  )
  return (
    <>
      <div className="page-intro"><div><p className="eyebrow">REVIEW / ANOMALY EVENTS</p><h1>Observed warnings & anomalies</h1><p>Events are based on incoming health and anomaly messages; suspected causes are not treated as confirmed faults.</p></div></div>
      <section className="panel anomaly-panel">
        <div className="anomaly-filters">
          <label>SEVERITY<select value={severity} onChange={(event) => setSeverity(event.currentTarget.value)}><option>ALL</option><option>CAUTION</option><option>WARNING</option><option>CRITICAL</option></select></label>
          <label>SOURCE<select value={source} onChange={(event) => setSource(event.currentTarget.value)}><option>ALL</option><option value="health">HEALTH SUMMARY</option><option value="anomaly">ANOMALY EVENT</option><option value="proposal">PLANNER</option></select></label>
          <span className="anomaly-total">{filtered.length} MATCHING · {items.length} LATCHED</span>
        </div>
        {filtered.length === 0 ? <p className="empty-state">No events match these filters.</p> : (
          <ul className="anomaly-list">
            {filtered.map((item) => (
              <li key={item.id} className={`anomaly-row anomaly-row--${item.severity.toLowerCase()}`}>
                <span className="anomaly-severity">{item.severity}</span>
                <div><strong>{item.title}</strong><p>{item.detail}</p><small>{utcTimeLabel(item.eventTimeMs)} · OBSERVED FROM {item.source.toUpperCase()} · {Math.max(0, (nowMs - item.receivedAt) / 1000).toFixed(0)} s ago · {item.active ? 'ACTIVE' : 'CLEARED'}</small></div>
                <span className="anomaly-review">Review source telemetry</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

function SettingsView() {
  return (
    <>
      <div className="page-intro"><div><p className="eyebrow">SYSTEM / SETTINGS</p><h1>Connection & display</h1><p>Current application configuration. These values are informational.</p></div></div>
      <section className="panel settings-panel">
        <div className="panel-heading"><div><p className="eyebrow">TELEMETRY TRANSPORT</p><h2>WebSocket endpoint</h2></div></div>
        <dl><dt>Endpoint</dt><dd><code>{telemetryWebSocketUrl()}</code></dd><dt>Source label</dt><dd>{isDefaultMockLink ? 'LOCAL FIXTURE STREAM' : 'CONFIGURED BACKEND · ENVIRONMENT UNKNOWN'}</dd><dt>Reconnect policy</dt><dd>Automatic backoff</dd><dt>High-rate frame storage</dt><dd>Mutable telemetry store; not React render state</dd></dl>
      </section>
    </>
  )
}

function ViewContent({ view }: { view: ViewId }) {
  switch (view) {
    case 'dashboard': return <OverviewView />
    case 'simulator': return <SimulatorView />
    case 'planner': return <PlannerView />
    case 'telemetry': return <LiveTelemetryView />
    case 'health': return <VehicleHealthView />
    case 'events': return <AnomalyEventsView />
    case 'control': return <FlightControlView />
    case 'replay': return <NotImplementedView title="Flight recorder / replay" description="No flight recording or log-ingest source is connected. Playback controls remain unavailable until recorded data is supported." status="RECORDER UNAVAILABLE · NO LOG SOURCE" />
    case 'audit': return <AuditPanel />
    case 'settings': return <SettingsView />
  }
}

export default function App() {
  const [view, setView] = useState<ViewId>(() => viewFromHash())
  const linkState = useTelemetryStore((state) => state.linkState)
  const mode = useTelemetryStore((state) => state.mode)
  const armed = useTelemetryStore((state) => state.armed)
  const missionSeq = useTelemetryStore((state) => state.missionSeq)
  const proposal = useTelemetryStore((state) => state.proposal)
  const [utcNow, setUtcNow] = useState('')

  useEffect(() => {
    const onHashChange = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHashChange)
    const stopTelemetry = connectTelemetry()
    const updateClock = () => setUtcNow(`${new Date().toISOString().slice(11, 19)}Z`)
    updateClock()
    const clockTimer = window.setInterval(updateClock, 1000)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
      window.clearInterval(clockTimer)
      stopTelemetry()
    }
  }, [])

  const groups = [...new Set(navigation.map(({ group }) => group))]
  const connectionState = connectionPresentation(linkState)
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#dashboard" aria-label="Tri Netra overview">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span className="brand-name">TRI NETRA<small>GROUND CONTROL</small></span>
        </a>
        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          {groups.map((group) => (
            <div className="nav-group" key={group}>
              <span className="nav-group__label">{group}</span>
              {navigation.filter((item) => item.group === group).map((item) => (
                <a className={`nav-link${view === item.id ? ' nav-link--active' : ''}`} href={`#${item.id}`} key={item.id} aria-current={view === item.id ? 'page' : undefined}>
                  <span className="nav-link__icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>
                  {item.id === 'simulator' && <span className="nav-link__tag">3D</span>}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <StatusLamp state={connectionState.state} label={linkState === 'connected' ? 'TELEMETRY LINK' : connectionState.label} />
          <small>{isDefaultMockLink ? 'LOCAL FIXTURE STREAM' : 'CONFIGURED BACKEND'}</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><strong>{navigation.find((item) => item.id === view)?.label}</strong></div>
          <div className="topbar-status">
            <span className="mission-clock mission-clock--name"><small>MISSION</small><strong>{proposal?.proposal_id ?? (missionSeq !== null ? `SEQ ${String(missionSeq).padStart(2, '0')}` : 'NO ACTIVE PLAN')}</strong></span>
            <span className="mission-clock mission-clock--time"><small>UTC</small><strong>{utcNow || '——:——:——'}</strong></span>
            <StatusLamp
              state={connectionState.state}
              label={linkState === 'connected' ? 'LINK OK' : linkState === 'connecting' ? 'LINK WAIT' : linkState === 'reconnecting' ? 'RETRYING' : 'LINK LOST'}
            />
            <span className="topbar-divider" />
            <span className="topbar-mode"><small>MODE</small><strong>{mode ?? '—'}</strong></span>
            <span className={`armed-indicator${armed ? ' armed-indicator--armed' : armed === null ? ' armed-indicator--unknown' : ''}`}><i aria-hidden="true" />{armed === null ? 'ARM UNKNOWN' : armed ? 'ARMED' : 'DISARMED'}</span>
          </div>
        </header>
        <main className="page-content"><ViewContent view={view} /></main>
        <footer className="app-footer"><span>TRI NETRA · MAVLINK GCS</span><span>ADVISORY DISPLAY · COMMANDS REQUIRE CONFIRMATION</span></footer>
      </div>
    </div>
  )
}
