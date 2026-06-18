export function clampFocalCoord(value: number): number {
  if (!Number.isFinite(value)) return 50
  return Math.max(0, Math.min(100, Math.round(value)))
}

export function focalObjectPosition(
  x: number | null | undefined,
  y: number | null | undefined,
): string {
  const cx = typeof x === 'number' && Number.isFinite(x) ? clampFocalCoord(x) : 50
  const cy = typeof y === 'number' && Number.isFinite(y) ? clampFocalCoord(y) : 50
  return `${cx}% ${cy}%`
}
