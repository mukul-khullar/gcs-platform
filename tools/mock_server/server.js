import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { WebSocketServer, WebSocket } from 'ws'

const FIXTURE_PATH = fileURLToPath(new URL('../../contracts/fixtures/stream.ndjson', import.meta.url))
const PORT = 8000
const TICK_MS = 50
const CIRCLE_RADIUS_M = 30
const CIRCLE_PERIOD_MS = 120000

export function synthesizeFrame(frame, elapsedMs, seq, wallMs, bootMs) {
  const phase = (elapsedMs / CIRCLE_PERIOD_MS) * Math.PI * 2
  const omega = (Math.PI * 2) / (CIRCLE_PERIOD_MS / 1000)
  const data = { ...frame.data }

  if (frame.type === 'telemetry.position') {
    const centerLat = frame.data.lat_deg
    const centerLon = frame.data.lon_deg
    const northM = CIRCLE_RADIUS_M * Math.cos(phase)
    const eastM = CIRCLE_RADIUS_M * Math.sin(phase)
    const latScale = 111320
    const lonScale = latScale * Math.cos((centerLat * Math.PI) / 180)
    const northMps = -CIRCLE_RADIUS_M * omega * Math.sin(phase)
    const eastMps = CIRCLE_RADIUS_M * omega * Math.cos(phase)

    Object.assign(data, {
      lat_deg: centerLat + northM / latScale,
      lon_deg: centerLon + eastM / lonScale,
      vel_ned_mps: [northMps, eastMps, 0],
      heading_deg: (((Math.atan2(eastMps, northMps) * 180) / Math.PI) + 360) % 360,
    })
  } else if (frame.type === 'telemetry.attitude') {
    data.roll_rad = 0.08 * Math.sin(phase)
    data.pitch_rad = 0.02 * Math.cos(phase)
    data.yaw_rad = ((phase + Math.PI / 2) % (Math.PI * 2)) - Math.PI
    data.rates_rps = [0, 0, omega]
  }

  return {
    ...frame,
    seq,
    t_wall_ms: wallMs,
    t_boot_ms: bootMs,
    data,
  }
}

export async function loadFixture(path = FIXTURE_PATH) {
  const contents = await readFile(path, 'utf8')
  return contents
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .map((line, index) => {
      try {
        return JSON.parse(line)
      } catch (error) {
        throw new Error(`Invalid JSON in fixture at line ${index + 1}`, { cause: error })
      }
    })
}

export async function createMockServer({ port = PORT, loop = false, fixturePath } = {}) {
  const fixture = await loadFixture(fixturePath)
  const attitudeTemplate = fixture.find((frame) => frame.type === 'telemetry.attitude')
  const positionTemplate = fixture.find((frame) => frame.type === 'telemetry.position')
  if (!attitudeTemplate || !positionTemplate) {
    throw new Error('Fixture must include telemetry.attitude and telemetry.position frames')
  }

  const replayFrames = fixture.filter(
    (frame) => frame.type !== 'telemetry.attitude' && frame.type !== 'telemetry.position',
  )
  const httpServer = createServer()
  const wsServer = new WebSocketServer({ noServer: true })
  let seq = 0
  let replayIndex = 0
  let tick = 0

  httpServer.on('upgrade', (request, socket, head) => {
    if (request.url !== '/ws/telemetry') {
      socket.destroy()
      return
    }
    wsServer.handleUpgrade(request, socket, head, (websocket) => {
      wsServer.emit('connection', websocket, request)
    })
  })

  const timer = setInterval(() => {
    const elapsedMs = tick * TICK_MS
    const wallMs = Date.now()
    const bootMs = elapsedMs
    tick += 1

    for (const client of wsServer.clients) {
      if (client.readyState !== WebSocket.OPEN) continue

      for (const template of [attitudeTemplate, positionTemplate]) {
        const frame = synthesizeFrame(template, elapsedMs, ++seq, wallMs, bootMs)
        client.send(JSON.stringify(frame))
      }

      if (replayIndex < replayFrames.length) {
        const source = replayFrames[replayIndex]
        client.send(
          JSON.stringify({
            ...source,
            seq: ++seq,
            t_wall_ms: wallMs,
            t_boot_ms: bootMs,
          }),
        )
        replayIndex += 1
        if (loop && replayIndex === replayFrames.length) replayIndex = 0
      }
    }
  }, TICK_MS)

  await new Promise((resolve, reject) => {
    httpServer.once('error', reject)
    httpServer.listen(port, resolve)
  })
  const address = httpServer.address()
  const listeningPort = typeof address === 'object' && address ? address.port : port
  console.log(`Mock telemetry server listening at ws://localhost:${listeningPort}/ws/telemetry${loop ? ' (looping)' : ''}`)

  return {
    port: listeningPort,
    async close() {
      clearInterval(timer)
      const clientClosures = Array.from(wsServer.clients, (client) => new Promise((resolve) => {
        client.once('close', resolve)
        client.close()
      }))
      await Promise.all(clientClosures)
      await new Promise((resolve, reject) => {
        httpServer.close((error) => error ? reject(error) : resolve())
      })
    },
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const loop = process.argv.includes('--loop')
  createMockServer({ loop }).catch((error) => {
    console.error('Failed to start mock telemetry server:', error)
    process.exitCode = 1
  })
}
