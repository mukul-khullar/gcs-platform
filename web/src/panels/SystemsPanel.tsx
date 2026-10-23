import { useTelemetryStore } from '../state/telemetryStore'
import type { FlightState, LinkState } from '../state/telemetryStore'

function stateFor(
  subsystem: string,
  subsystems: Record<string, { state: FlightState; reasons: string[] }>,
  link: LinkState,
): string {
  if (subsystem === 'link') {
    return link === 'connected' ? (subsystems.link?.state ?? 'GO') : 'CAUTION'
  }
  return subsystems[subsystem]?.state ?? 'UNKNOWN'
}

function varianceFor(reasons: string[] | undefined): number | null {
  for (const reason of reasons ?? []) {
    const match = reason.match(/variance[^\d]*(\d+(?:\.\d+)?)/i)
    if (match) return Number(match[1])
  }
  return null
}

function StateValue({ state }: { state: string }) {
  return <span className={`system-state system-state--${state.toLowerCase()}`}>{state}</span>
}

export function SystemsPanel() {
  const subsystems = useTelemetryStore((state) => state.subsystems)
  const linkState = useTelemetryStore((state) => state.linkState)
  const ekf = subsystems.ekf
  const variance = varianceFor(ekf?.reasons)
  const variancePercent = variance === null ? 0 : Math.max(0, Math.min(100, (variance / 1.2) * 100))
  const varianceTone = variance === null
    ? 'unknown'
    : variance >= 1
      ? 'critical'
      : variance >= 0.8
        ? 'warning'
        : 'go'
  const systems = [
    { id: 'batt', label: 'BATTERY' },
    { id: 'gps', label: 'GPS' },
    { id: 'link', label: 'LINK' },
  ]

  return (
    <article className="panel systems-panel">
      <div className="panel__heading">
        <div><p className="eyebrow">SENSOR &amp; POWER</p><h2>Systems monitor</h2></div>
        <span className="panel__index">04</span>
      </div>
      <div className="ekf-monitor">
        <div className="system-row">
          <span className="system-name">EKF VARIANCE</span>
          <StateValue state={stateFor('ekf', subsystems, linkState)} />
        </div>
        <div
          className={`variance-meter variance-meter--${varianceTone}`}
          role="meter"
          aria-label="EKF variance"
          aria-valuemin={0}
          aria-valuemax={1.2}
          aria-valuenow={variance ?? 0}
          aria-valuetext={variance === null ? 'No variance data' : `${variance.toFixed(2)} variance`}
        >
          <div className="variance-meter__track">
            <span className="variance-meter__fill" style={{ width: `${variancePercent}%` }} />
            {[0.5, 0.8, 1.0].map((mark) => (
              <span
                className="variance-meter__mark"
                key={mark}
                style={{ left: `${(mark / 1.2) * 100}%` }}
                aria-hidden="true"
              />
            ))}
          </div>
          <div className="variance-meter__scale">
            <span>0</span><span>0.5</span><span>0.8</span><span>1.0</span><span>1.2</span>
          </div>
        </div>
        <div className="variance-readout">
          <strong className={`variance-readout--${varianceTone}`}>{variance === null ? '—' : variance.toFixed(2)}</strong>
          <span>HORIZONTAL VARIANCE</span>
        </div>
      </div>
      <div className="systems-list">
        {systems.map(({ id, label }) => {
          const state = stateFor(id, subsystems, linkState)
          const reasons = subsystems[id]?.reasons ?? []
          return (
            <div className="system-row" key={id}>
              <div>
                <span className="system-name">{label}</span>
                {reasons[0] && <p className="system-reason">{reasons[0]}</p>}
              </div>
              <StateValue state={state} />
            </div>
          )
        })}
      </div>
      <div className="systems-footnote">Variance alert marks: 0.5 CAUTION / 0.8 WARNING / 1.0 CRITICAL</div>
    </article>
  )
}
