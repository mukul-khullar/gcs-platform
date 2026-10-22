import { useTelemetryStore } from '../state/telemetryStore'

export function AuditPanel() {
  const entries = useTelemetryStore((state) => state.auditLog)

  return (
    <section className="panel audit-panel" aria-label="Command and mission audit log">
      <div className="panel__heading">
        <div><p className="eyebrow">LOCAL SESSION RECORD</p><h2>Action audit</h2></div>
        <span className="panel__count">{String(entries.length).padStart(2, '0')}</span>
      </div>
      {entries.length === 0 ? (
        <p className="audit-empty">Command, planning, and upload actions will be recorded here.</p>
      ) : (
        <ol className="audit-list">
          {entries.map((entry) => (
            <li className={`audit-entry audit-entry--${entry.result.toLowerCase()}`} key={entry.id}>
              <time dateTime={new Date(entry.at).toISOString()}>
                {new Date(entry.at).toLocaleTimeString([], { hour12: false })}
              </time>
              <strong>{entry.action}</strong>
              <span>{entry.detail}</span>
              <b>{entry.result}</b>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
