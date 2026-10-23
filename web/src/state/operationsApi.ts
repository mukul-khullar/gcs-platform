import { z } from 'zod'

const prepareResponseSchema = z.object({
  confirm_token: z.string().min(1),
  expires_s: z.number().positive(),
  summary: z.string().min(1),
})

const planResponseSchema = z.object({ proposal_id: z.string().min(1) })
const uploadResponseSchema = z.object({
  proposal_id: z.string().optional(),
  state: z.string().optional(),
}).passthrough()

export type CommandAction = 'arm' | 'mode' | 'rtl'
export type CommandParams = Record<string, never> | { mode: 'AUTO' }
export type PrepareResponse = z.infer<typeof prepareResponseSchema>

export type PlanRequest = {
  request_id: string
  vehicle: { cruise_mps: number; battery_wh: number; reserve_pct: number }
  start: { lat_deg: number; lon_deg: number; alt_rel_m: number }
  goals: { lat_deg: number; lon_deg: number; alt_rel_m: number }[]
  constraints: {
    geofence: [number, number][]
    no_fly: { polygon: [number, number][]; floor_m: number; ceil_m: number }[]
    min_alt_m: number
    max_alt_m: number
    max_waypoints: number
  }
  environment: { wind_from_deg: number; wind_mps: number }
}

async function postJson<T>(path: string, body: unknown, schema: z.ZodType<T>): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (error) {
    throw new Error(`Request to ${path} failed: ${error instanceof Error ? error.message : String(error)}`)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error(`${path} returned a non-JSON response (HTTP ${response.status})`)
  }

  if (!response.ok) {
    const message = z.object({ detail: z.string().optional(), message: z.string().optional() }).safeParse(payload)
    throw new Error(message.success ? message.data.detail ?? message.data.message ?? `HTTP ${response.status}` : `HTTP ${response.status}`)
  }

  const parsed = schema.safeParse(payload)
  if (!parsed.success) {
    throw new Error(`${path} response did not match the API contract`)
  }
  return parsed.data
}

export function prepareCommand(action: CommandAction, params: CommandParams): Promise<PrepareResponse> {
  return postJson('/api/v1/command/prepare', { action, params }, prepareResponseSchema)
}

export function executeCommand(
  action: CommandAction,
  confirmToken: string,
  params: CommandParams,
): Promise<unknown> {
  return postJson(`/api/v1/command/${action}`, { confirm_token: confirmToken, params }, z.unknown())
}

export function submitPlan(request: PlanRequest): Promise<z.infer<typeof planResponseSchema>> {
  return postJson('/api/v1/mission/plan', request, planResponseSchema)
}

export function uploadMission(proposalId: string, approvedBy: string): Promise<z.infer<typeof uploadResponseSchema>> {
  return postJson('/api/v1/mission/upload', { proposal_id: proposalId, approved_by: approvedBy }, uploadResponseSchema)
}
