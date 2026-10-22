import { z } from 'zod'

const stateSchema = z.enum(['GO', 'CAUTION', 'WARNING', 'CRITICAL'])
const envelope = {
  v: z.literal(1),
  seq: z.number().int(),
  sysid: z.number().int(),
  t_wall_ms: z.number().int(),
  t_boot_ms: z.number().int(),
}

const frameSchemas = [
  z.object({
    ...envelope,
    type: z.literal('telemetry.attitude'),
    data: z.object({
      roll_rad: z.number(),
      pitch_rad: z.number(),
      yaw_rad: z.number(),
      rates_rps: z.tuple([z.number(), z.number(), z.number()]),
    }),
  }),
  z.object({
    ...envelope,
    type: z.literal('telemetry.position'),
    data: z.object({
      lat_deg: z.number(),
      lon_deg: z.number(),
      alt_msl_m: z.number(),
      alt_rel_m: z.number(),
      vel_ned_mps: z.tuple([z.number(), z.number(), z.number()]),
      heading_deg: z.number(),
    }),
  }),
  z.object({
    ...envelope,
    type: z.literal('vehicle.status'),
    data: z.object({
      armed: z.boolean(),
      mode: z.string(),
      system_status: z.string(),
      mission_seq: z.number().int(),
    }),
  }),
  z.object({
    ...envelope,
    type: z.literal('health.summary'),
    data: z.object({
      overall: stateSchema,
      subsystems: z.record(
        z.string(),
        z.object({ state: stateSchema, reasons: z.array(z.string()) }),
      ),
    }),
  }),
  z.object({
    ...envelope,
    type: z.literal('anomaly.event'),
    data: z.object({
      id: z.string(),
      severity: stateSchema,
      signals: z.array(z.string()),
      score: z.number(),
      explanation: z.string(),
    }),
  }),
  z.object({
    ...envelope,
    type: z.literal('mission.proposal'),
    data: z.object({
      proposal_id: z.string(),
      waypoints: z.array(z.object({
        seq: z.number().int(),
        lat_deg: z.number(),
        lon_deg: z.number(),
        alt_rel_m: z.number(),
        speed_mps: z.number(),
      })),
      metrics: z.object({
        length_m: z.number(),
        eta_s: z.number(),
        energy_wh: z.number(),
        min_clearance_m: z.number(),
      }),
      violations: z.array(z.object({ code: z.string(), message: z.string() })),
      explain: z.array(z.string()),
    }),
  }),
  z.object({
    ...envelope,
    type: z.literal('mission.state'),
    data: z.object({
      proposal_id: z.string(),
      state: z.enum(['uploading', 'accepted', 'failed']),
      items_sent: z.number().int(),
      items_total: z.number().int(),
      error: z.string().nullable().optional(),
    }),
  }),
] as const

export const telemetryFrameSchema = z.discriminatedUnion('type', frameSchemas)
export type TelemetryFrame = z.infer<typeof telemetryFrameSchema>
