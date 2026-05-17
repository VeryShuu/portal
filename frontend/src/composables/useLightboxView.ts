import { computed, ref } from 'vue'

export function useLightboxView() {
  const zoom = ref(1)
  const rotation = ref(0)

  const imgStyle = computed(() => ({
    transform: `rotate(${rotation.value}deg) scale(${zoom.value})`,
    transition: 'transform 0.15s ease-out',
  }))

  function resetView() { zoom.value = 1; rotation.value = 0 }
  function zoomIn() { zoom.value = Math.min(8, +(zoom.value + 0.25).toFixed(2)) }
  function zoomOut() { zoom.value = Math.max(0.25, +(zoom.value - 0.25).toFixed(2)) }
  function rotateLeft() { rotation.value = (rotation.value - 90) % 360 }
  function rotateRight() { rotation.value = (rotation.value + 90) % 360 }

  let _wheelRafPending = false
  function onLightboxWheel(e: WheelEvent) {
    if (_wheelRafPending) return
    _wheelRafPending = true
    requestAnimationFrame(() => { _wheelRafPending = false })
    if (e.deltaY < 0) zoomIn(); else zoomOut()
  }

  return { zoom, rotation, imgStyle, resetView, zoomIn, zoomOut, rotateLeft, rotateRight, onLightboxWheel }
}
