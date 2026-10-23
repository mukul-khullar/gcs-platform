import { telemetryFrameSchema } from './protocol'
import { recordFrame, useTelemetryStore } from './telemetryStore'

const INITIAL_RETRY_MS = 500
const MAX_RETRY_MS = 15000

export function telemetryWebSocketUrl(): string {
  const configuredUrl = import.meta.env.VITE_TELEMETRY_WS_URL as string | undefined
  if (configuredUrl) return configuredUrl
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//localhost:8000/ws/telemetry`
}

export function connectTelemetry(): () => void {
  let socket: WebSocket | null = null
  let retryTimer: number | undefined
  let startupTimer: number | undefined
  let retryDelay = INITIAL_RETRY_MS
  let stopped = false
  const store = useTelemetryStore.getState()

  const connect = () => {
    if (stopped) return
    store.setLinkState(retryDelay === INITIAL_RETRY_MS ? 'connecting' : 'reconnecting')
    const connection = new WebSocket(telemetryWebSocketUrl())
    socket = connection

    connection.addEventListener('open', () => {
      if (stopped || socket !== connection) return
      retryDelay = INITIAL_RETRY_MS
      useTelemetryStore.getState().setLinkState('connected')
    })

    connection.addEventListener('message', (event: MessageEvent<string>) => {
      if (stopped || socket !== connection) return
      let payload: unknown
      try {
        payload = JSON.parse(event.data)
      } catch {
        useTelemetryStore.getState().setProtocolError('Received malformed JSON from telemetry link')
        return
      }

      const parsed = telemetryFrameSchema.safeParse(payload)
      if (!parsed.success) {
        useTelemetryStore.getState().setProtocolError('Received a frame outside the telemetry contract')
        return
      }

      useTelemetryStore.getState().setProtocolError('')
      recordFrame(parsed.data, performance.now())
    })

    connection.addEventListener('close', () => {
      if (stopped || socket !== connection) return
      useTelemetryStore.getState().setLinkState('reconnecting')
      const jitter = Math.random() * retryDelay * 0.2
      retryTimer = window.setTimeout(connect, retryDelay + jitter)
      retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS)
    })

    connection.addEventListener('error', () => connection.close())
  }

  store.setLinkState('connecting')
  startupTimer = window.setTimeout(() => {
    startupTimer = undefined
    connect()
  }, 0)
  return () => {
    stopped = true
    if (startupTimer !== undefined) window.clearTimeout(startupTimer)
    if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    socket?.close()
    useTelemetryStore.getState().setLinkState('disconnected')
  }
}
