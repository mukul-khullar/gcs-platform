import { useEffect, useState } from 'react'
import { connectTelemetry } from './state/telemetryClient'
import { telemetryFrames, useTelemetryStore } from './state/telemetryStore'
import type { FlightState, LinkState } from './state/telemetryStore'
import { Pfd } from './instruments/Pfd'
import { TacticalMap } from './map/TacticalMap'
import { SystemsPanel } from './panels/SystemsPanel'
import { AuditPanel } from './panels/AuditPanel'
import { CommandBar } from './panels/CommandBar'
import { PlanPanel } from './panels/PlanPanel'
import { DEMO_GEOFENCE, DEMO_NO_FLY_ZONES } from './state/demoPlan'
import './App.css'

const linkLabels: Record<LinkState, string> = {
  connecting: 'CONNECTING',
  connected: 'LINK ACTIVE',
  reconnecting: 'RECONNECTING',
  disconnected: 'LINK CLOSED',
}

function StatusLamp({ state, label }: { state: string; label: string }) {
  const tone =
    state === 'GO' || state === 'connected' || state === 'ARMED'
      ? 'go'
      : state === 'WARNING' || state === 'CRITICAL' || state === 'disconnected'
        ? 'warning'
        : state === 'CAUTION' || state === 'connecting' || state === 'reconnecting'
          ? 'caution'
          : 'neutral'
  const icon = tone === 'go' ? '✓' : tone === 'warning' ? '!' : tone === 'caution' ? '↻' : '·'

  return (
    <span className={`status-lamp status-lamp--${tone}`}>
      <span className="status-lamp__icon" aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </span>
  )
}

function formatAge(ageMs: number | null): string {
  if (ageMs === null) return 'NO DATA'
  if (ageMs < 1000) return `${Math.max(0, Math.floor(ageMs))} ms`
  return `${(ageMs / 1000).toFixed(1)} s`
}

function App() {
  const linkState = useTelemetryStore((state) => state.linkState)
  const mode = useTelemetryStore((state) => state.mode)
  const armed = useTelemetryStore((state) => state.armed)
  const health = useTelemetryStore((state) => state.health)
  const cwsItems = useTelemetryStore((state) => state.cwsItems)
  const acknowledgeAlerts = useTelemetryStore((state) => state.acknowledgeAlerts)
  const protocolError = useTelemetryStore((state) => state.protocolError)
  const unacknowledged = cwsItems.filter((item) => !item.acknowledged)
  const masterSeverity = unacknowledged.reduce<FlightState>((highest, item) => {
    const rank: Record<FlightState, number> = { GO: 0, CAUTION: 1, WARNING: 2, CRITICAL: 3 }
    return rank[item.severity] > rank[highest] ? item.severity : highest
  }, 'GO')
  const [ageMs, setAgeMs] = useState<number | null>(null)

  useEffect(() => {
    const disconnect = connectTelemetry()
    const ageTimer = window.setInterval(() => {
      const receivedAt = telemetryFrames.lastReceivedAt
      setAgeMs(receivedAt === null ? null : performance.now() - receivedAt)
    }, 250)
    return () => {
      disconnect()
      window.clearInterval(ageTimer)
    }
  }, [])

  return (
    <main className="flight-deck">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Northstar ground control home">
          <span className="brand__mark" aria-hidden="true">N</span>
          <span className="brand__name">NORTHSTAR</span>
          <span className="brand__divider" />
          <span className="brand__context">FLIGHT SYSTEMS</span>
        </a>
        <div className="topbar__right">
          <span className="live-indicator"><span /> LIVE TELEMETRY</span>
          <span className="topbar__system">SYS 01</span>
        </div>
      </header>

      <section className="mission-heading" aria-labelledby="mission-title">
        <div>
          <p className="eyebrow">VEHICLE OVERVIEW <span> / </span> SYSTEM MONITOR</p>
          <h1 id="mission-title">Flight status</h1>
        </div>
        <StatusLamp state={health ?? 'neutral'} label={health ?? 'HEALTH UNKNOWN'} />
      </section>

      <section className="status-bar" aria-label="Vehicle status">
        <div className="status-bar__cell status-bar__link">
          <span className="status-bar__label">TELEMETRY LINK</span>
          <StatusLamp state={linkState} label={linkLabels[linkState]} />
        </div>
        <div className="status-bar__cell">
          <span className="status-bar__label">FLIGHT MODE</span>
          <strong>{mode}</strong>
        </div>
        <div className="status-bar__cell">
          <span className="status-bar__label">MOTOR STATE</span>
          <StatusLamp
            state={armed === null ? 'neutral' : armed ? 'ARMED' : 'DISARMED'}
            label={armed === null ? 'UNKNOWN' : armed ? 'ARMED' : 'DISARMED'}
          />
        </div>
        <div className="status-bar__cell status-bar__age">
          <span className="status-bar__label">DATA AGE</span>
          <strong>{formatAge(ageMs)}</strong>
        </div>
      </section>

      <section className="overview-grid">
        <article className="panel health-panel">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">SYSTEMS</p>
              <h2>Vehicle health</h2>
            </div>
            <span className="panel__index">01</span>
          </div>
          <div className="health-state">
            <div className={`health-state__symbol health-state__symbol--${(health ?? 'unknown').toLowerCase()}`}>
              {health === 'GO' ? '✓' : health ? '!' : '·'}
            </div>
            <div>
              <span className="eyebrow">OVERALL STATE</span>
              <p>{health ?? 'Awaiting health summary'}</p>
            </div>
          </div>
          <div className="health-note">
            <span className="health-note__icon" aria-hidden="true">i</span>
            Advisory display only <span className="health-note__dot">·</span> Commands require bridge confirmation
          </div>
        </article>

        <article className="panel cws-panel">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">CREW WARNING SYSTEM</p>
              <h2>Alerts &amp; cautions</h2>
            </div>
            <span className="panel__count">{String(cwsItems.length).padStart(2, '0')}</span>
          </div>
          <div
            className={`master-alarm master-alarm--${unacknowledged.length ? masterSeverity.toLowerCase() : 'clear'}`}
            role={unacknowledged.length ? 'alert' : 'status'}
            aria-live="polite"
          >
            <div>
              <strong>{unacknowledged.length ? `MASTER ${masterSeverity}` : 'MASTER ALARM CLEAR'}</strong>
              <span>
                {unacknowledged.length
                  ? `${unacknowledged.length} annunciator${unacknowledged.length === 1 ? '' : 's'} require acknowledgement`
                  : 'No unacknowledged annunciators'}
              </span>
            </div>
            <button
              className="acknowledge-button"
              type="button"
              onClick={() => {
                acknowledgeAlerts()
                useTelemetryStore.getState().logAudit('CWS · ACKNOWLEDGE', 'INFO', 'Operator acknowledged active annunciators')
              }}
              disabled={unacknowledged.length === 0}
            >
              ACKNOWLEDGE
            </button>
          </div>
          {protocolError && (
            <div className="protocol-error" role="alert">
              <StatusLamp state="WARNING" label="PROTOCOL" />
              <span>{protocolError}</span>
            </div>
          )}
          {cwsItems.length === 0 && !protocolError ? (
            <div className="empty-state">
              <span className="empty-state__icon" aria-hidden="true">✓</span>
              <div>
                <strong>No active cautions</strong>
                <p>System messages will appear here</p>
              </div>
            </div>
          ) : (
            <ul className="alert-list">
              {cwsItems.map((item) => (
                <li
                  className={`alert-item${item.acknowledged ? ' alert-item--acknowledged' : ''}${!item.active ? ' alert-item--cleared' : ''}`}
                  key={`${item.id}:${item.escalation}`}
                  data-severity={item.severity}
                >
                  <div className="alert-item__heading">
                    <StatusLamp state={item.severity satisfies FlightState} label={item.title} />
                    <span className="alert-item__state">
                      {!item.active ? 'CLEARED · ACK REQUIRED' : item.acknowledged ? 'ACKNOWLEDGED' : 'UNACKNOWLEDGED'}
                    </span>
                  </div>
                  <p>{item.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>

      <section className="systems-section" aria-label="Sensor and power systems">
        <SystemsPanel />
      </section>

      <section className="instruments-grid" aria-label="Flight instruments and tactical map">
        <article className="panel instrument-panel">
          <div className="panel__heading">
            <div><p className="eyebrow">FLIGHT INSTRUMENTS</p><h2>Primary flight display</h2></div>
            <span className="panel__index">02</span>
          </div>
          <Pfd />
        </article>
        <article className="panel instrument-panel">
          <div className="panel__heading">
            <div><p className="eyebrow">NAVIGATION</p><h2>Tactical map</h2></div>
            <span className="panel__index">03</span>
          </div>
          <TacticalMap geofence={DEMO_GEOFENCE} noFlyZones={DEMO_NO_FLY_ZONES} sampleGeometry />
        </article>
      </section>

      <section className="operations-grid" aria-label="Command and mission operations">
        <CommandBar />
        <PlanPanel />
      </section>

      <AuditPanel />

      <footer className="footer">
        <span>GROUND CONTROL <span className="footer__separator">/</span> ADVISORY CONSOLE</span>
        <span>TELEMETRY FRAMES HELD IN LOCAL MEMORY</span>
      </footer>
    </main>
  )
}

export default App
