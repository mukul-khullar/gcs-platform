import { afterEach, describe, expect, it, vi } from 'vitest'
import { executeCommand, prepareCommand, type CommandParams } from '../src/state/operationsApi'
import { isProposalStale } from '../src/state/planPolicy'

describe('command API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('prepares with an allow-listed command and executes only with the returned token', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        confirm_token: 'one-use-token',
        expires_s: 60,
        summary: 'Set mode to AUTO',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const params: CommandParams = { mode: 'AUTO' }
    const prepared = await prepareCommand('mode', params)
    await executeCommand('mode', prepared.confirm_token, params)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/command/prepare', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ action: 'mode', params }),
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/command/mode', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ confirm_token: 'one-use-token', params }),
    }))
  })

  it('surfaces prepare rejection details and does not send the command', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: 'Arm checks failed',
    }), { status: 409 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(prepareCommand('arm', {})).rejects.toThrow('Arm checks failed')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('proposal freshness', () => {
  it('is stale strictly after sixty seconds', () => {
    expect(isProposalStale(1000, 61000)).toBe(false)
    expect(isProposalStale(1000, 61001)).toBe(true)
  })
})
