import { describe, expect, it } from 'vitest'
import { acknowledgeCws, reduceCws, type CwsItem } from '../src/state/cwsReducer'

const health = (state: 'GO' | 'CAUTION' | 'WARNING' | 'CRITICAL', reasons: string[] = []) => ({
  type: 'health.summary' as const,
  data: {
    overall: state,
    subsystems: { ekf: { state, reasons } },
  },
})

describe('CWS reducer', () => {
  it('latches an annunciator and does not flash repeats at the same severity', () => {
    const first = reduceCws([], health('CAUTION', ['variance 0.6']), 100)
    const timestamped = reduceCws([], health('WARNING'), 200, 1700000000000)
    const repeated = reduceCws(first, health('CAUTION', ['variance 0.6']), 200)

    expect(first).toHaveLength(1)
    expect(first[0]).toMatchObject({ id: 'health:ekf', active: true, acknowledged: false, escalation: 1 })
    expect(timestamped[0].eventTimeMs).toBe(1700000000000)
    expect(repeated[0].escalation).toBe(1)
  })

  it('acknowledges active alerts and removes acknowledged alerts after recovery', () => {
    const active = reduceCws([], health('WARNING', ['variance 0.9']), 100)
    const acknowledged = acknowledgeCws(active)
    const recovered = reduceCws(acknowledged, health('GO'), 200)

    expect(acknowledged[0].acknowledged).toBe(true)
    expect(recovered).toEqual([])
  })

  it('keeps a recovered alert latched until it is acknowledged', () => {
    const active = reduceCws([], health('WARNING', ['variance 0.9']), 100)
    const recovered = reduceCws(active, health('GO'), 200)

    expect(recovered).toHaveLength(1)
    expect(recovered[0]).toMatchObject({ severity: 'WARNING', active: false, acknowledged: false })
    expect(acknowledgeCws(recovered)).toEqual([])
  })

  it('de-escalates severity without flashing, then flashes a new escalation', () => {
    const warning = reduceCws([], health('WARNING', ['variance 0.9']), 100)
    const caution = reduceCws(warning, health('CAUTION', ['variance 0.6']), 200)
    const acknowledged = acknowledgeCws(caution)
    const repeated = reduceCws(acknowledged, health('CAUTION', ['variance 0.6']), 250)
    const escalated = reduceCws(repeated, health('CRITICAL', ['variance 1.1']), 300)

    expect(caution[0]).toMatchObject({ severity: 'CAUTION', escalation: 1 })
    expect(repeated[0].acknowledged).toBe(true)
    expect(repeated[0].escalation).toBe(1)
    expect(escalated[0]).toMatchObject({ severity: 'CRITICAL', escalation: 2, acknowledged: false })
  })

  it('latches anomaly events by id and updates only on severity escalation', () => {
    const anomaly = (severity: 'WARNING' | 'CRITICAL') => ({
      type: 'anomaly.event' as const,
      data: {
        id: 'ANOM-7',
        severity,
        signals: ['ekf'],
        score: 0.9,
        explanation: 'Position variance increasing',
      },
    })
    const first = reduceCws([], anomaly('WARNING'), 100)
    const repeated = reduceCws(first, anomaly('WARNING'), 200)
    const escalated = reduceCws(repeated, anomaly('CRITICAL'), 300)
    const acknowledged: CwsItem[] = acknowledgeCws(escalated)

    expect(repeated).toHaveLength(1)
    expect(repeated[0].escalation).toBe(1)
    expect(escalated[0]).toMatchObject({ severity: 'CRITICAL', escalation: 2 })
    expect(acknowledged).toEqual([])
  })
})
