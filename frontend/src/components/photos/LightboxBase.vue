<template>
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
  <div
    v-if="open"
    class="lightbox"
    role="dialog"
    aria-modal="true"
    :aria-label="ariaLabel"
    @click.self="emitClose"
    @keydown.escape="emitClose"
    @wheel.prevent="(e) => emit('wheel', e)"
  >
    <button
      class="lightbox__close"
      :title="closeTitle"
      @click="emitClose"
    >
      ✕
    </button>
    <button
      v-if="total > 1"
      class="lightbox__nav lightbox__nav--prev"
      :title="prevTitle"
      @click="onPrev"
    >
      ‹
    </button>

    <slot />

    <button
      v-if="total > 1"
      class="lightbox__nav lightbox__nav--next"
      :title="nextTitle"
      @click="onNext"
    >
      ›
    </button>

    <slot name="toolbar" />
    <slot name="info" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  modelValue: number | null
  total: number
  loop?: boolean
  ariaLabel?: string
  closeTitle?: string
  prevTitle?: string
  nextTitle?: string
}>(), {
  loop: true,
  ariaLabel: 'Lightbox',
  closeTitle: undefined,
  prevTitle: undefined,
  nextTitle: undefined,
})

const emit = defineEmits<{
  (e: 'update:modelValue', idx: number | null): void
  (e: 'close'): void
  (e: 'prev'): void
  (e: 'next'): void
  (e: 'wheel', ev: WheelEvent): void
  (e: 'keydown', ev: KeyboardEvent): void
}>()

const { t } = useI18n()
const open = computed(() => props.modelValue !== null)

const closeTitle = computed(() => props.closeTitle ?? t('common.close'))
const prevTitle = computed(() => props.prevTitle ?? t('common.prev'))
const nextTitle = computed(() => props.nextTitle ?? t('common.next'))

function emitClose() {
  emit('close')
  emit('update:modelValue', null)
}

function onPrev() {
  if (props.modelValue === null || props.total === 0) return
  const next = props.modelValue - 1
  const wrapped = next < 0 ? (props.loop ? props.total - 1 : 0) : next
  emit('update:modelValue', wrapped)
  emit('prev')
}

function onNext() {
  if (props.modelValue === null || props.total === 0) return
  const next = props.modelValue + 1
  const wrapped = next >= props.total ? (props.loop ? 0 : props.total - 1) : next
  emit('update:modelValue', wrapped)
  emit('next')
}

const previouslyFocusedElement = ref<HTMLElement | null>(null)
const focusTimer = ref<ReturnType<typeof setTimeout> | null>(null)

function focusableElements(): HTMLElement[] {
  const root = document.querySelector('.lightbox')
  if (!root) return []
  const sel = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  return Array.from(root.querySelectorAll(sel)) as HTMLElement[]
}

function handleTab(e: KeyboardEvent) {
  const focusable = focusableElements()
  if (focusable.length === 0) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement as HTMLElement | null
  if (e.shiftKey) {
    if (active === first || !active || !focusable.includes(active)) {
      e.preventDefault(); last.focus()
    }
  } else {
    if (active === last || !active || !focusable.includes(active)) {
      e.preventDefault(); first.focus()
    }
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (!open.value) return
  if (e.key === 'Tab') {
    handleTab(e)
    return
  }
  const target = e.target as HTMLElement | null
  if (target) {
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable) {
      emit('keydown', e)
      return
    }
  }
  if (e.key === 'Escape') { emitClose() }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); onPrev() }
  else if (e.key === 'ArrowRight') { e.preventDefault(); onNext() }
  else { emit('keydown', e) }
}

function clearFocusTimer() {
  if (focusTimer.value !== null) {
    clearTimeout(focusTimer.value)
    focusTimer.value = null
  }
}

watch(() => props.modelValue, (newVal) => {
  if (newVal !== null) {
    previouslyFocusedElement.value = document.activeElement as HTMLElement | null
    clearFocusTimer()
    focusTimer.value = setTimeout(() => {
      focusTimer.value = null
      const closeBtn = document.querySelector('.lightbox__close') as HTMLElement | null
      if (closeBtn) closeBtn.focus()
    }, 50)
  } else {
    // Лайтбокс закрылся — отложенный фокус на close-button больше не нужен.
    // Без этого таймер протекает (запускается в уже уничтоженном окружении
    // при размонтировании — ReferenceError: document is not defined).
    clearFocusTimer()
    const prev = previouslyFocusedElement.value
    if (prev && typeof prev.focus === 'function') prev.focus()
    previouslyFocusedElement.value = null
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  clearFocusTimer()
})
</script>

<style scoped>
.lightbox {
  position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 1500;
  display: flex; align-items: center; justify-content: center;
}
.lightbox__close, .lightbox__nav {
  position: absolute; background: rgba(255,255,255,0.1); color: #fff;
  border: 0; cursor: pointer; font-size: 24px;
  width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; z-index: 2;
}
.lightbox__close { top: 16px; right: 16px; }
.lightbox__nav--prev { left: 16px; top: 50%; transform: translateY(-50%); }
.lightbox__nav--next { right: 16px; top: 50%; transform: translateY(-50%); }
</style>
