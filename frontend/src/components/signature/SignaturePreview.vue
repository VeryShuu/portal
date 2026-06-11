<template>
  <div class="signature-preview">
    <div
      v-if="!html"
      class="signature-preview__empty"
    >
      {{ t('signature.preview.empty') }}
    </div>
    <iframe
      v-else
      ref="frame"
      class="signature-preview__frame"
      :srcdoc="html"
      title="signature preview"
      sandbox="allow-same-origin"
      scrolling="no"
      @load="resize"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  html: string
}>()

const { t } = useI18n()
const frame = ref<HTMLIFrameElement | null>(null)

function resize(): void {
  const el = frame.value
  const doc = el?.contentDocument
  if (!el || !doc?.body) return
  el.style.height = `${doc.body.scrollHeight}px`
}

watch(
  () => props.html,
  () => nextTick(resize),
)
</script>

<style scoped>
.signature-preview {
  border: 1px solid var(--color-border, #e0e0e6);
  border-radius: 8px;
  background: #fff;
  min-height: 220px;
  padding: 16px;
}
.signature-preview__empty {
  color: var(--color-text-muted, #999);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 188px;
  text-align: center;
}
.signature-preview__frame {
  width: 100%;
  min-height: 300px;
  border: 0;
  background: #fff;
}
</style>
