import type { CSSProperties } from 'vue'

export function clampFocalCoord(value: number): number {
  if (!Number.isFinite(value)) return 50
  return Math.max(0, Math.min(100, Math.round(value)))
}

export function clampFocalZoom(value: number): number {
  if (!Number.isFinite(value)) return 100
  return Math.max(100, Math.min(300, Math.round(value)))
}

export function focalObjectPosition(
  x: number | null | undefined,
  y: number | null | undefined,
): string {
  const cx = typeof x === 'number' && Number.isFinite(x) ? clampFocalCoord(x) : 50
  const cy = typeof y === 'number' && Number.isFinite(y) ? clampFocalCoord(y) : 50
  return `${cx}% ${cy}%`
}

export function focalImageStyle(
  x: number | null | undefined,
  y: number | null | undefined,
  zoom: number | null | undefined,
): CSSProperties {
  const cx = typeof x === 'number' && Number.isFinite(x) ? clampFocalCoord(x) : 50
  const cy = typeof y === 'number' && Number.isFinite(y) ? clampFocalCoord(y) : 50
  const z = typeof zoom === 'number' && Number.isFinite(zoom) ? clampFocalZoom(zoom) : 100
  const scale = z / 100
  return {
    objectPosition: `${cx}% ${cy}%`,
    transform: scale === 1 ? 'none' : `scale(${scale})`,
    transformOrigin: `${cx}% ${cy}%`,
  }
}
