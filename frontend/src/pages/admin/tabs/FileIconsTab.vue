<template>
  <div>
    <div class="tab-toolbar">
      <span class="hint">{{ t('admin.fileIcons.hint') }}</span>
      <n-button
        style="margin-left:auto"
        type="primary"
        @click="openAdd"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.fileIcons.add') }}
      </n-button>
    </div>

    <div
      v-if="!rows.length"
      class="empty"
    >
      {{ t('admin.fileIcons.empty') }}
    </div>

    <ul
      v-else
      class="icon-list"
    >
      <li
        v-for="row in rows"
        :key="row.extension"
        class="icon-row"
      >
        <div class="icon-row__preview">
          <img
            :src="row.url"
            :alt="row.extension"
            class="icon-row__img"
          >
        </div>
        <div class="icon-row__main">
          <div class="icon-row__ext">
            .{{ row.extension }}
          </div>
          <div class="icon-row__src">
            <span
              v-if="row.source === 'custom'"
              class="badge badge--custom"
            >{{ t('admin.fileIcons.custom') }}</span>
            <span
              v-else
              class="badge badge--bundled"
            >{{ t('admin.fileIcons.bundled') }}</span>
          </div>
        </div>
        <n-button
          size="small"
          @click="openReplace(row.extension)"
        >
          {{ t('admin.fileIcons.replace') }}
        </n-button>
        <n-button
          v-if="row.source === 'custom'"
          size="small"
          type="error"
          ghost
          :loading="deleting === row.extension"
          @click="onDelete(row.extension)"
        >
          <template #icon>
            <n-icon><TrashOutline /></n-icon>
          </template>
          {{ t('common.delete') }}
        </n-button>
      </li>
    </ul>

    <n-modal
      v-model:show="modalOpen"
      :title="editingExt ? t('admin.fileIcons.replaceTitle', { ext: editingExt }) : t('admin.fileIcons.addTitle')"
      preset="card"
      style="width:440px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        :model="form"
        label-placement="top"
      >
        <n-form-item
          v-if="!editingExt"
          :label="t('admin.fileIcons.extLabel')"
        >
          <n-input
            v-model:value="form.extension"
            :placeholder="t('admin.fileIcons.extPlaceholder')"
            maxlength="16"
          />
        </n-form-item>
        <n-form-item :label="t('admin.fileIcons.fileLabel')">
          <input
            ref="fileInputRef"
            type="file"
            accept="image/svg+xml,.svg"
            @change="onFileChange"
          >
        </n-form-item>
        <div
          v-if="previewUrl"
          class="preview"
        >
          <img
            :src="previewUrl"
            class="preview__img"
            alt="preview"
          >
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="modalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :disabled="!canSubmit"
            :loading="uploading"
            @click="submit"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  NButton, NForm, NFormItem, NIcon, NInput, NModal,
} from 'naive-ui'
import { AddOutline, TrashOutline } from '@vicons/ionicons5'
import { useFileIconsStore } from '../../../stores/fileIcons'

const { t } = useI18n()
const message = useMessage()
const store = useFileIconsStore()

interface Row {
  extension: string
  url: string
  source: 'custom' | 'bundled'
}

const rows = computed<Row[]>(() => {
  const map = new Map<string, Row>()
  for (const [ext, url] of Object.entries(store.bundledIcons)) {
    map.set(ext, { extension: ext, url, source: 'bundled' })
  }
  for (const [ext, url] of Object.entries(store.customByExt)) {
    map.set(ext, { extension: ext, url, source: 'custom' })
  }
  return [...map.values()].sort((a, b) => a.extension.localeCompare(b.extension))
})

const modalOpen = ref(false)
const editingExt = ref<string | null>(null)
const form = ref({ extension: '' })
const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const previewUrl = ref<string | null>(null)
const uploading = ref(false)
const deleting = ref<string | null>(null)

const canSubmit = computed(() => {
  if (!selectedFile.value) return false
  const ext = (editingExt.value ?? form.value.extension).trim().toLowerCase()
  return /^[a-z0-9]{1,16}$/.test(ext)
})

function resetForm(): void {
  form.value = { extension: '' }
  selectedFile.value = null
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function openAdd(): void {
  editingExt.value = null
  resetForm()
  modalOpen.value = true
}

function openReplace(ext: string): void {
  editingExt.value = ext
  resetForm()
  form.value.extension = ext
  modalOpen.value = true
}

function onFileChange(e: Event): void {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = null
  if (!file) {
    selectedFile.value = null
    return
  }
  if (!/svg/i.test(file.type) && !file.name.toLowerCase().endsWith('.svg')) {
    message.error(t('admin.fileIcons.svgOnly'))
    input.value = ''
    selectedFile.value = null
    return
  }
  if (file.size > 64 * 1024) {
    message.error(t('admin.fileIcons.tooBig'))
    input.value = ''
    selectedFile.value = null
    return
  }
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
}

async function submit(): Promise<void> {
  if (!selectedFile.value) return
  const ext = (editingExt.value ?? form.value.extension).trim().toLowerCase().replace(/^\./, '')
  if (!/^[a-z0-9]{1,16}$/.test(ext)) {
    message.error(t('admin.fileIcons.badExt'))
    return
  }
  uploading.value = true
  try {
    await store.upload(ext, selectedFile.value)
    message.success(t('common.saved'))
    modalOpen.value = false
    resetForm()
  } catch (err) {
    console.error(err)
    message.error(t('common.errorOccurred'))
  } finally {
    uploading.value = false
  }
}

async function onDelete(ext: string): Promise<void> {
  deleting.value = ext
  try {
    await store.remove(ext)
    message.success(t('common.deleted'))
  } catch (err) {
    console.error(err)
    message.error(t('common.errorOccurred'))
  } finally {
    deleting.value = null
  }
}

onMounted(() => {
  store.refresh()
})
</script>

<style scoped>
@import '../admin-tabs.css';

.hint {
  font-size: 13px;
  color: var(--color-text-muted);
}

.empty {
  padding: 24px;
  text-align: center;
  color: var(--color-text-muted);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.icon-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.icon-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.icon-row__preview {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-row__img {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.icon-row__main {
  flex: 1;
  min-width: 0;
}

.icon-row__ext {
  font-weight: 600;
}

.icon-row__src {
  margin-top: 2px;
}

.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}

.badge--custom {
  background: var(--color-brand-red-soft, #fde2e2);
  color: var(--color-brand-red, #c0392b);
}

.badge--bundled {
  background: var(--color-bg-muted, #eee);
  color: var(--color-text-muted, #666);
}

.preview {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.preview__img {
  width: 64px;
  height: 64px;
  object-fit: contain;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
