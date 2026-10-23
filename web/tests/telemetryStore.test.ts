import { afterEach, describe, expect, it } from 'vitest'
import { useTelemetryStore } from '../src/state/telemetryStore'

describe('telemetry CWS acknowledgement', () => {
  afterEach(() => useTelemetryStore.setState({ cwsItems: [] }))

  it('acknowledges only the selected active annunciator', () => {
    useTelemetryStore.setState({
      cwsItems: [
        {
          id: 'active',
          source: 'health',
          severity: 'WARNING',
          title: 'GPS WARNING',
          detail: 'Accuracy degraded',
          receivedAt: 1,
          eventTimeMs: 1001,
          active: true,
          acknowledged: false,
          escalation: 1,
        },
        {
          id: 'cleared',
          source: 'health',
          severity: 'CAUTION',
          title: 'BATTERY CAUTION',
          detail: 'Battery state recovered',
          receivedAt: 2,
          eventTimeMs: 1002,
          active: false,
          acknowledged: false,
          escalation: 1,
        },
      ],
    })

    useTelemetryStore.getState().acknowledgeCwsItem('active')

    const items = useTelemetryStore.getState().cwsItems
    expect(items.find((item) => item.id === 'active')?.acknowledged).toBe(true)
    expect(items.find((item) => item.id === 'cleared')?.acknowledged).toBe(false)
  })

  it('allows acknowledgement of a recovered item that remains latched', () => {
    useTelemetryStore.setState({
      cwsItems: [{
        id: 'cleared',
        source: 'health',
        severity: 'CAUTION',
        title: 'BATTERY CAUTION',
        detail: 'Battery state recovered',
        receivedAt: 2,
        eventTimeMs: 1002,
        active: false,
        acknowledged: false,
        escalation: 1,
      }],
    })

    useTelemetryStore.getState().acknowledgeCwsItem('cleared')

    expect(useTelemetryStore.getState().cwsItems[0]?.acknowledged).toBe(true)
  })

  it('acknowledges every latched item with the master action', () => {
    useTelemetryStore.setState({
      cwsItems: [
        {
          id: 'active',
          source: 'health',
          severity: 'WARNING',
          title: 'GPS WARNING',
          detail: 'Accuracy degraded',
          receivedAt: 1,
          eventTimeMs: 1001,
          active: true,
          acknowledged: false,
          escalation: 1,
        },
        {
          id: 'recovered',
          source: 'anomaly',
          severity: 'CAUTION',
          title: 'ANOMALY A-1',
          detail: 'Signal recovered',
          receivedAt: 2,
          eventTimeMs: 1002,
          active: false,
          acknowledged: false,
          escalation: 1,
        },
      ],
    })

    useTelemetryStore.getState().acknowledgeAllCwsItems()

    expect(useTelemetryStore.getState().cwsItems.every((item) => item.acknowledged)).toBe(true)
  })
})
