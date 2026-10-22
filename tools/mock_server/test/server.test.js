import assert from 'node:assert/strict'
import test from 'node:test'
import WebSocket from 'ws'
import { createMockServer, synthesizeFrame } from '../server.js'

const positionFrame = {
  v: 1,
  type: 'telemetry.position',
  seq: 2,
  sysid: 1,
  t_wall_ms: 1000,
  t_boot_ms: 500,
  data: {
    lat_deg: 31.634,
    lon_deg: 74.8723,
    alt_msl_m: 251,
    alt_rel_m: 50,
    vel_ned_mps: [5, 2, 0],
    heading_deg: 87,
  },
}

test('synthetic position moves on a slow circle and refreshes frame clocks', () => {
  const first = synthesizeFrame(positionFrame, 0, 10, 2000, 900)
  const later = synthesizeFrame(positionFrame, 10000, 11, 12000, 10900)

  assert.notEqual(first.data.lat_deg, later.data.lat_deg)
  assert.notEqual(first.data.lon_deg, later.data.lon_deg)
  assert.equal(first.seq, 10)
  assert.equal(first.t_wall_ms, 2000)
  assert.equal(first.t_boot_ms, 900)
  assert.equal(first.data.vel_ned_mps.length, 3)
})

test('synthetic attitude changes with circle heading', () => {
  const first = synthesizeFrame(
    { ...positionFrame, type: 'telemetry.attitude', data: { roll_rad: 0, pitch_rad: 0, yaw_rad: 0, rates_rps: [0, 0, 0] } },
    0,
    1,
    1000,
    500,
  )
  const later = synthesizeFrame(
    { ...positionFrame, type: 'telemetry.attitude', data: { roll_rad: 0, pitch_rad: 0, yaw_rad: 0, rates_rps: [0, 0, 0] } },
    10000,
    2,
    11000,
    10500,
  )

  assert.notEqual(first.data.yaw_rad, later.data.yaw_rad)
})

test('websocket endpoint streams synthesized frames and replays fixture events', async () => {
  const server = await createMockServer({ port: 0, loop: true })
  const socket = new WebSocket(`ws://localhost:${server.port}/ws/telemetry`)
  const frames = []

  try {
    await new Promise((resolve, reject) => {
      socket.once('open', resolve)
      socket.once('error', reject)
    })
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Timed out waiting for telemetry')), 1000)
      socket.on('message', (message) => {
        frames.push(JSON.parse(message.toString()))
        if (frames.some((frame) => frame.type === 'vehicle.status')) {
          clearTimeout(timeout)
          resolve()
        }
      })
    })

    assert.ok(frames.some((frame) => frame.type === 'telemetry.attitude'))
    assert.ok(frames.some((frame) => frame.type === 'telemetry.position'))
    assert.ok(frames.some((frame) => frame.type === 'vehicle.status'))
  } finally {
    socket.close()
    await new Promise((resolve) => socket.once('close', resolve))
    await server.close()
  }
})
