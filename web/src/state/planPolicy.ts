export const PROPOSAL_MAX_AGE_MS = 60_000

export function isProposalStale(receivedAt: number, now: number): boolean {
  return now - receivedAt > PROPOSAL_MAX_AGE_MS
}
