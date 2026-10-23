export function pitchToPixels(pitchRad: number, pixelsPerRad: number): number {
  return pitchRad * pixelsPerRad
}

export function wrapAngleRad(angleRad: number): number {
  return ((angleRad + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI
}
