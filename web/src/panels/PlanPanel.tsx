import { useEffect, useState } from 'react'
import { telemetryFrames, useTelemetryStore } from '../state/telemetryStore'
import { buildDemoPlanRequest } from '../state/demoPlan'
import { isProposalStale, PROPOSAL_MAX_AGE_MS } from '../state/planPolicy'
import { submitPlan, uploadMission } from '../state/operationsApi'

export function PlanPanel() {
  const proposal = useTelemetryStore((state) => state.proposal)
  const proposalReceivedAt = useTelemetryStore((state) => state.proposalReceivedAt)
  const missionState = useTelemetryStore((state) => state.missionState)
  const logAudit = useTelemetryStore((state) => state.logAudit)
  const [requestedId, setRequestedId] = useState('')
  const [approvedBy, setApprovedBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [now, setNow] = useState(() => performance.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(performance.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const visibleProposal = proposal && (!requestedId || proposal.proposal_id === requestedId) ? proposal : null
  const receivedAt = visibleProposal ? proposalReceivedAt : null
  const stale = receivedAt === null || isProposalStale(receivedAt, now)
  const ageMs = receivedAt === null ? null : Math.max(0, now - receivedAt)
  const hasViolations = !!visibleProposal && visibleProposal.violations.length > 0
  const waitingForProposal = requestedId !== '' && visibleProposal === null
  const uploadState = missionState && visibleProposal && missionState.proposal_id === visibleProposal.proposal_id
    ? missionState.state
    : null
  const ageLabel = ageMs === null ? '—' : `${Math.floor(ageMs / 1000)} s`

  const createPlan = async () => {
    setBusy(true)
    setError('')
    setRequestedId('')
    const position = telemetryFrames.position?.data
    const start = position
      ? { lat_deg: position.lat_deg, lon_deg: position.lon_deg, alt_rel_m: position.alt_rel_m }
      : { lat_deg: 31.634, lon_deg: 74.8723, alt_rel_m: 30 }
    logAudit('PLAN · SUBMIT', 'INFO', 'Submitting illustrative-profile mission plan request')
    try {
      const response = await submitPlan(buildDemoPlanRequest(start))
      setRequestedId(response.proposal_id)
      logAudit('PLAN · REQUESTED', 'SUCCESS', `Proposal ${response.proposal_id}; awaiting proposal details`)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      logAudit('PLAN · FAILED', 'ERROR', message)
    } finally {
      setBusy(false)
    }
  }

  const approve = async () => {
    if (!visibleProposal || stale || hasViolations || approvedBy.trim() === '') return
    setBusy(true)
    setError('')
    logAudit('MISSION · APPROVE', 'INFO', `Uploading proposal ${visibleProposal.proposal_id}`)
    try {
      await uploadMission(visibleProposal.proposal_id, approvedBy.trim())
      logAudit('MISSION · UPLOAD ACCEPTED', 'SUCCESS', `Proposal ${visibleProposal.proposal_id} accepted by bridge`)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      logAudit('MISSION · UPLOAD REJECTED', 'ERROR', message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel plan-panel" aria-label="Mission planning">
      <div className="panel__heading">
        <div><p className="eyebrow">ROUTE OPTIMIZATION</p><h2>Mission proposal</h2></div>
        <span className="panel__index">06</span>
      </div>
      <div className="illustrative-profile-note" role="note">
        ILLUSTRATIVE PROFILE · Sample vehicle, goal, geofence, and wind values. Not flight validated.
      </div>
      <p className="plan-profile-detail">
        Start uses live position when available. This profile supplies a sample goal, vehicle capacity, altitude limits, geofence and no-fly area.
      </p>
      <button className="plan-button" type="button" onClick={() => void createPlan()} disabled={busy}>
        {busy ? 'WORKING…' : 'GENERATE SAMPLE PLAN'}
      </button>
      {error && <p className="operation-error" role="alert">{error}</p>}
      {waitingForProposal && <p className="plan-waiting">Waiting for proposal details from telemetry…</p>}
      {visibleProposal && (
        <div className="proposal-content">
          <div className="proposal-heading">
            <strong>PROPOSAL {visibleProposal.proposal_id}</strong>
            <span className={stale ? 'proposal-age proposal-age--stale' : 'proposal-age'}>
              {stale ? `STALE · ${ageLabel}` : `AGE ${ageLabel}`}
            </span>
          </div>
          <dl className="proposal-metrics">
            <div><dt>DISTANCE</dt><dd>{visibleProposal.metrics.length_m.toFixed(0)} m</dd></div>
            <div><dt>ETA</dt><dd>{visibleProposal.metrics.eta_s.toFixed(0)} s</dd></div>
            <div><dt>ENERGY</dt><dd>{visibleProposal.metrics.energy_wh.toFixed(1)} Wh</dd></div>
            <div><dt>MIN CLEARANCE</dt><dd>{visibleProposal.metrics.min_clearance_m.toFixed(1)} m</dd></div>
          </dl>
          <div className="proposal-detail-grid">
            <div>
              <h3>VIOLATIONS · {visibleProposal.violations.length}</h3>
              {visibleProposal.violations.length
                ? <ul className="proposal-violations">{visibleProposal.violations.map((item, index) => <li key={`${item.code}:${index}`}><strong>{item.code}</strong> {item.message}</li>)}</ul>
                : <p className="proposal-clear">No planner violations reported</p>}
            </div>
            <div>
              <h3>EXPLANATION</h3>
              <ul className="proposal-explain">{visibleProposal.explain.map((item, index) => <li key={`${index}:${item}`}>{item}</li>)}</ul>
            </div>
          </div>
          {uploadState && <p className="plan-waiting">MISSION STATE · {uploadState.toUpperCase()}</p>}
          <label className="operator-label" htmlFor="approved-by">APPROVED BY · OPERATOR ID</label>
          <input
            id="approved-by"
            className="operator-input"
            value={approvedBy}
            onChange={(event) => setApprovedBy(event.currentTarget.value)}
            placeholder="Enter operator ID"
            autoComplete="off"
          />
          <button
            className="plan-button plan-button--approve"
            type="button"
            onClick={() => void approve()}
            disabled={busy || stale || hasViolations || !visibleProposal || approvedBy.trim() === ''}
          >
            APPROVE &amp; UPLOAD
          </button>
          {hasViolations && <p className="approve-block-reason">Upload blocked: resolve all planner violations first.</p>}
          {stale && <p className="approve-block-reason">Upload blocked: regenerate the proposal; approval window is 60 seconds.</p>}
        </div>
      )}
      {requestedId && !visibleProposal && <p className="plan-waiting">Request accepted · {requestedId}</p>}
      <span className="proposal-window" aria-hidden="true">{PROPOSAL_MAX_AGE_MS / 1000}s approval window</span>
    </section>
  )
}
