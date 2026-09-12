import { describe, expect, it } from 'vitest'
import { useLightboxView } from '@/composables/useLightboxView'

describe('useLightboxView (#F-4)', () => {
  it('initial state: zoom=1, rotation=0', () => {
    const v = useLightboxView()
    expect(v.zoom.value).toBe(1)
    expect(v.rotation.value).toBe(0)
    expect(v.imgStyle.value.transform).toBe('rotate(0deg) scale(1)')
  })

  it('zoomIn caps at 8', () => {
    const v = useLightboxView()
    for (let i = 0; i < 100; i++) v.zoomIn()
    expect(v.zoom.value).toBe(8)
  })

  it('zoomOut floors at 0.25', () => {
    const v = useLightboxView()
    for (let i = 0; i < 100; i++) v.zoomOut()
    expect(v.zoom.value).toBe(0.25)
  })

  it('zoomIn/zoomOut step is 0.25 and rounded to 2 decimals', () => {
    const v = useLightboxView()
    v.zoomIn()
    expect(v.zoom.value).toBe(1.25)
    v.zoomIn()
    expect(v.zoom.value).toBe(1.5)
    v.zoomOut()
    expect(v.zoom.value).toBe(1.25)
  })

  it('rotateLeft/rotateRight by 90deg, modulo 360', () => {
    const v = useLightboxView()
    v.rotateRight()
    expect(v.rotation.value).toBe(90)
    v.rotateRight()
    expect(v.rotation.value).toBe(180)
    v.rotateRight()
    expect(v.rotation.value).toBe(270)
    v.rotateRight()
    expect(v.rotation.value).toBe(0)
    v.rotateLeft()
    expect(v.rotation.value).toBe(-90)
  })

  it('resetView restores zoom=1, rotation=0', () => {
    const v = useLightboxView()
    v.zoomIn(); v.zoomIn(); v.rotateRight()
    v.resetView()
    expect(v.zoom.value).toBe(1)
    expect(v.rotation.value).toBe(0)
  })

  it('imgStyle reflects current zoom and rotation', () => {
    const v = useLightboxView()
    v.zoomIn()
    v.rotateRight()
    expect(v.imgStyle.value.transform).toBe('rotate(90deg) scale(1.25)')
  })

  it('onLightboxWheel with deltaY<0 zooms in', () => {
    const v = useLightboxView()
    v.onLightboxWheel(new WheelEvent('wheel', { deltaY: -10 }))
    expect(v.zoom.value).toBe(1.25)
  })

  it('onLightboxWheel with deltaY>0 zooms out', () => {
    const v = useLightboxView()
    v.onLightboxWheel(new WheelEvent('wheel', { deltaY: 10 }))
    expect(v.zoom.value).toBe(0.75)
  })
})
