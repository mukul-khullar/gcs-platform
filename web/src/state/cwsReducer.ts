import type { TelemetryFrame } from './protocol'

type HealthData = Extract<TelemetryFrame, { type: 'health.summary' }>['data']
export type CwsSeverity = Exclude<HealthData['overall'], 'GO'>
export type CwsSource = 'health' | 'anomaly' | 'proposal'
export type CwsItem = {
  id: string
  source: CwsSource
  severity: CwsSeverity
  title: string
  detail: string
  receivedAt: number
  active: boolean
  acknowledged: boolean
  escalation: number
}

type AnomalyData = Extract<TelemetryFrame, { type: 'anomaly.event' }>['data']
type ProposalData = Extract<TelemetryFrame, { type: 'mission.proposal' }>['data']

export type CwsEvent =
  | { type: 'health.summary'; data: HealthData }
  | { type: 'anomaly.event'; data: AnomalyData }
  | { type: 'mission.proposal'; data: ProposalData }

const severityRank: Record<CwsSeverity, number> = {
  CAUTION: 1,
  WARNING: 2,
  CRITICAL: 3,
}

function upsert(
  items: CwsItem[],
  input: Omit<CwsItem, 'active' | 'acknowledged' | 'escalation'>,
): CwsItem[] {
  const existing = items.find((item) => item.id === input.id)
  const escalated = existing !== undefined && severityRank[input.severity] > severityRank[existing.severity]
  const item: CwsItem = {
    ...input,
    active: true,
    acknowledged: escalated ? false : (existing?.acknowledged ?? false),
    escalation: existing ? existing.escalation + (escalated ? 1 : 0) : 1,
  }
  return [...items.filter((current) => current.id !== input.id), item]
}

function reduceHealth(items: CwsItem[], data: HealthData, receivedAt: number): CwsItem[] {
  const activeIds = new Set(
    Object.entries(data.subsystems)
      .filter(([, subsystem]) => subsystem.state !== 'GO')
      .map(([name]) => `health:${name}`),
  )
  let next = items.map((item) =>
    item.source === 'health' && !activeIds.has(item.id)
      ? { ...item, active: false, receivedAt }
      : item,
  )
  next = next.filter((item) => item.active || !item.acknowledged)

  for (const [name, subsystem] of Object.entries(data.subsystems)) {
    if (subsystem.state === 'GO') continue
    next = upsert(next, {
      id: `health:${name}`,
      source: 'health',
      severity: subsystem.state,
      title: `${name.toUpperCase()} ${subsystem.state}`,
      detail: subsystem.reasons.join(' · ') || `${name.toUpperCase()} reports ${subsystem.state}`,
      receivedAt,
    })
  }
  return next
}

export function reduceCws(items: CwsItem[], event: CwsEvent, receivedAt: number): CwsItem[] {
  if (event.type === 'health.summary') return reduceHealth(items, event.data, receivedAt)
  if (event.type === 'anomaly.event') {
    if (event.data.severity === 'GO') return items
    return upsert(items, {
      id: event.data.id,
      source: 'anomaly',
      severity: event.data.severity,
      title: `ANOMALY ${event.data.id}`,
      detail: event.data.explanation,
      receivedAt,
    })
  }

  return event.data.violations.reduce(
    (next, violation, index) => upsert(next, {
      id: `proposal:${event.data.proposal_id}:${index}`,
      source: 'proposal',
      severity: 'WARNING',
      title: `PLAN ${violation.code}`,
      detail: violation.message,
      receivedAt,
    }),
    items,
  )
}

export function acknowledgeCws(items: CwsItem[]): CwsItem[] {
  return items
    .filter((item) => item.source === 'health' && item.active)
    .map((item) => ({ ...item, acknowledged: true }))
}
