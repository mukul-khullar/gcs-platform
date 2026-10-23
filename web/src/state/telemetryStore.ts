import { create } from 'zustand'
import { acknowledgeCws, reduceCws } from './cwsReducer'
import type { CwsItem } from './cwsReducer'
import type { TelemetryFrame } from './protocol'
import { appendPositionSample } from './telemetryHistory'
import type { PositionSample } from './telemetryHistory'

export type LinkState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected'
export type FlightState = 'GO' | 'CAUTION' | 'WARNING' | 'CRITICAL'

type HealthSubsystems = Extract<TelemetryFrame, { type: 'health.summary' }>['data']['subsystems']
type MissionProposal = Extract<TelemetryFrame, { type: 'mission.proposal' }>['data']
export type AuditResult = 'INFO' | 'SUCCESS' | 'ERROR'
export type AuditEntry = {
  id: number
  at: number
  action: string
  result: AuditResult
  detail: string
}

interface TelemetryState {
  linkState: LinkState
  mode: string
  missionSeq: number | null
  armed: boolean | null
  health: FlightState | null
  subsystems: HealthSubsystems
  cwsItems: CwsItem[]
  proposal: MissionProposal | null
  proposalReceivedAt: number | null
  missionState: Extract<TelemetryFrame, { type: 'mission.state' }>['data'] | null
  auditLog: AuditEntry[]
  protocolError: string | null
  setLinkState: (linkState: LinkState) => void
  setProtocolError: (message: string) => void
  acknowledgeAlerts: () => void
  acknowledgeCwsItem: (id: string) => void
  acknowledgeAllCwsItems: () => void
  logAudit: (action: string, result: AuditResult, detail: string) => void
  ingest: (frame: TelemetryFrame, receivedAt: number) => void
}

export const useTelemetryStore = create<TelemetryState>((set) => ({
  linkState: 'connecting',
  mode: '—',
  missionSeq: null,
  armed: null,
  health: null,
  subsystems: {},
  cwsItems: [],
  proposal: null,
  proposalReceivedAt: null,
  missionState: null,
  auditLog: [],
  protocolError: null,
  setLinkState: (linkState) => set({ linkState }),
  setProtocolError: (protocolError) => set({ protocolError }),
  acknowledgeAlerts: () => set((state) => ({ cwsItems: acknowledgeCws(state.cwsItems) })),
  acknowledgeCwsItem: (id) => set((state) => ({
    cwsItems: state.cwsItems.map((item) =>
      item.id === id ? { ...item, acknowledged: true } : item,
    ),
  })),
  acknowledgeAllCwsItems: () => set((state) => ({
    cwsItems: state.cwsItems.map((item) => ({ ...item, acknowledged: true })),
  })),
  logAudit: (action, result, detail) => set((state) => ({
    auditLog: [
      { id: (state.auditLog[0]?.id ?? 0) + 1, at: Date.now(), action, result, detail },
      ...state.auditLog,
    ].slice(0, 40),
  })),
  ingest: (frame, receivedAt) => {
    if (frame.type === 'vehicle.status') {
      set({ mode: frame.data.mode, armed: frame.data.armed, missionSeq: frame.data.mission_seq })
      return
    }

    if (frame.type === 'health.summary') {
      set((state) => ({
        health: frame.data.overall,
        subsystems: frame.data.subsystems,
        cwsItems: reduceCws(state.cwsItems, frame, receivedAt, frame.t_wall_ms),
      }))
      return
    }

    if (frame.type === 'anomaly.event' || frame.type === 'mission.proposal') {
      set((state) => ({
        cwsItems: reduceCws(state.cwsItems, frame, receivedAt, frame.t_wall_ms),
        ...(frame.type === 'mission.proposal'
          ? { proposal: frame.data, proposalReceivedAt: receivedAt }
          : {}),
      }))
      return
    }

    if (frame.type === 'mission.state') {
      set({ missionState: frame.data })
      return
    }
  },
}))

export const telemetryFrames: {
  attitude: Extract<TelemetryFrame, { type: 'telemetry.attitude' }> | null
  attitudeReceivedAt: number | null
  position: Extract<TelemetryFrame, { type: 'telemetry.position' }> | null
  positionReceivedAt: number | null
  lastReceivedAt: number | null
  positionHistory: PositionSample[]
} = {
  attitude: null,
  attitudeReceivedAt: null,
  position: null,
  positionReceivedAt: null,
  lastReceivedAt: null,
  positionHistory: [],
}

export function recordFrame(frame: TelemetryFrame, receivedAt: number): void {
  if (frame.type === 'telemetry.attitude') {
    telemetryFrames.attitude = frame
    telemetryFrames.attitudeReceivedAt = receivedAt
  }
  if (frame.type === 'telemetry.position') {
    telemetryFrames.position = frame
    telemetryFrames.positionReceivedAt = receivedAt
    telemetryFrames.positionHistory = appendPositionSample(
      telemetryFrames.positionHistory,
      frame,
      receivedAt,
    )
  }
  telemetryFrames.lastReceivedAt = receivedAt
  useTelemetryStore.getState().ingest(frame, receivedAt)
}
