<template>
  <div class="dir-settings">
    <div class="dir-settings__bar">
      <n-select
        v-model:value="selectedId"
        :options="typeOptions"
        :placeholder="t('directories.admin.selectType')"
        class="dir-settings__select"
      />
      <n-button
        type="primary"
        @click="startNew"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('directories.admin.newType') }}
      </n-button>
    </div>

    <div
      v-if="!editing"
      class="empty-hint"
    >
      {{ t('directories.admin.pickHint') }}
    </div>

    <n-form
      v-else
      label-placement="top"
    >
      <div class="row-2">
        <n-form-item
          :label="t('directories.admin.slug')"
          required
        >
          <n-input
            v-model:value="editing.slug"
            :disabled="!isNew"
            placeholder="fleet"
          />
        </n-form-item>
        <n-form-item :label="t('directories.admin.icon')">
          <n-input
            v-model:value="editing.icon"
            placeholder="boat"
            clearable
          />
        </n-form-item>
      </div>
      <div class="row-2">
        <n-form-item
          :label="t('directories.admin.labelRu')"
          required
        >
          <n-input v-model:value="editing.label_ru" />
        </n-form-item>
        <n-form-item :label="t('directories.admin.labelEn')">
          <n-input
            v-model:value="editing.label_en"
            clearable
          />
        </n-form-item>
      </div>
      <n-form-item :label="t('directories.admin.description')">
        <n-input
          v-model:value="editing.description"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 3 }"
          clearable
        />
      </n-form-item>
      <n-form-item>
        <n-checkbox v-model:checked="editing.enabled">
          {{ t('directories.admin.enabled') }}
        </n-checkbox>
      </n-form-item>

      <n-divider class="section-divider">
        {{ t('directories.admin.fields') }}
      </n-divider>
      <div
        v-for="(f, idx) in editing.field_schema"
        :key="`f-${idx}`"
        class="schema-row"
      >
        <div class="schema-row__grid">
          <n-input
            v-model:value="f.key"
            size="small"
            :placeholder="t('directories.admin.fieldKey')"
          />
          <n-input
            v-model:value="f.label_ru"
            size="small"
            :placeholder="t('directories.admin.labelRu')"
          />
          <n-input
            v-model:value="f.label_en"
            size="small"
            :placeholder="t('directories.admin.labelEn')"
          />
          <n-select
            v-model:value="f.type"
            size="small"
            :options="fieldTypeOptions"
          />
          <n-checkbox v-model:checked="f.required">
            {{ t('directories.admin.required') }}
          </n-checkbox>
        </div>
        <n-button
          size="small"
          quaternary
          circle
          @click="editing.field_schema.splice(idx, 1)"
        >
          <template #icon>
            <n-icon><TrashOutline /></n-icon>
          </template>
        </n-button>
      </div>
      <n-button
        size="small"
        dashed
        block
        class="add-row"
        @click="addField"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('directories.admin.addField') }}
      </n-button>

      <n-divider class="section-divider">
        {{ t('directories.admin.channels') }}
      </n-divider>
      <div
        v-for="(c, idx) in editing.channels"
        :key="`c-${idx}`"
        class="schema-row"
      >
        <div class="schema-row__grid schema-row__grid--channel">
          <n-input
            v-model:value="c.key"
            size="small"
            :placeholder="t('directories.admin.fieldKey')"
          />
          <n-input
            v-model:value="c.label_ru"
            size="small"
            :placeholder="t('directories.admin.labelRu')"
          />
          <n-input
            v-model:value="c.label_en"
            size="small"
            :placeholder="t('directories.admin.labelEn')"
          />
        </div>
        <n-button
          size="small"
          quaternary
          circle
          @click="editing.channels.splice(idx, 1)"
        >
          <template #icon>
            <n-icon><TrashOutline /></n-icon>
          </template>
        </n-button>
      </div>
      <n-button
        size="small"
        dashed
        block
        class="add-row"
        @click="addChannel"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('directories.admin.addChannel') }}
      </n-button>

      <div class="dir-settings__actions">
        <n-button
          v-if="!isNew"
          quaternary
          type="error"
          :loading="deleting"
          @click="onDelete"
        >
          {{ t('common.delete') }}
        </n-button>
        <div class="footer-spacer" />
        <n-button
          type="primary"
          :loading="saving"
          :disabled="!canSave"
          @click="onSave"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NCheckbox, NDivider, NForm, NFormItem, NIcon, NInput, NSelect,
  useMessage,
} from 'naive-ui'
import { AddOutline, TrashOutline } from '@vicons/ionicons5'
import type {
  DirectoryChannel, DirectoryField, DirectoryPublic, FieldType,
} from '../../api/directories'
import {
  useDirectoriesQuery, useCreateDirectoryMutation, useUpdateDirectoryMutation,
  useDeleteDirectoryMutation,
} from '../../queries/directories'

const { t } = useI18n()
const message = useMessage()

const directoriesQuery = useDirectoriesQuery()
const createMutation = useCreateDirectoryMutation()
const updateMutation = useUpdateDirectoryMutation()
const deleteMutation = useDeleteDirectoryMutation()

const directories = computed<DirectoryPublic[]>(() => directoriesQuery.data.value?.items ?? [])

const selectedId = ref<string | null>(null)
const isNew = ref(false)
const saving = ref(false)
const deleting = ref(false)

interface EditState {
  id: string | null
  slug: string
  label_ru: string
  label_en: string
  icon: string
  description: string
  enabled: boolean
  field_schema: DirectoryField[]
  channels: DirectoryChannel[]
}

const editing = ref<EditState | null>(null)

const typeOptions = computed(() =>
  directories.value.map((d) => ({ label: `${d.label_ru} (${d.slug})`, value: d.id })),
)

const fieldTypeOptions: { label: string; value: FieldType }[] = [
  { label: 'text', value: 'text' },
  { label: 'number', value: 'number' },
  { label: 'email', value: 'email' },
  { label: 'url', value: 'url' },
  { label: 'multiline', value: 'multiline' },
]

const canSave = computed(
  () => !!editing.value && !!editing.value.slug.trim() && !!editing.value.label_ru.trim(),
)

function toEdit(d: DirectoryPublic): EditState {
  return {
    id: d.id,
    slug: d.slug,
    label_ru: d.label_ru,
    label_en: d.label_en ?? '',
    icon: d.icon ?? '',
    description: d.description ?? '',
    enabled: d.enabled,
    field_schema: d.field_schema.map((f) => ({ ...f })),
    channels: d.channels.map((c) => ({ ...c })),
  }
}

watch(selectedId, (id) => {
  if (!id) return
  const found = directories.value.find((d) => d.id === id)
  if (found) {
    isNew.value = false
    editing.value = toEdit(found)
  }
})

function startNew() {
  selectedId.value = null
  isNew.value = true
  editing.value = {
    id: null,
    slug: '',
    label_ru: '',
    label_en: '',
    icon: '',
    description: '',
    enabled: true,
    field_schema: [],
    channels: [],
  }
}

function addField() {
  editing.value?.field_schema.push({
    key: '',
    label_ru: '',
    label_en: '',
    type: 'text',
    required: false,
    sort_order: editing.value.field_schema.length,
  })
}

function addChannel() {
  editing.value?.channels.push({
    key: '',
    label_ru: '',
    label_en: '',
    sort_order: editing.value.channels.length,
  })
}

function normalize() {
  const e = editing.value!
  return {
    label_ru: e.label_ru.trim(),
    label_en: e.label_en.trim() || null,
    icon: e.icon.trim() || null,
    description: e.description.trim() || null,
    enabled: e.enabled,
    field_schema: e.field_schema.map((f, i) => ({
      key: f.key.trim(),
      label_ru: f.label_ru.trim(),
      label_en: f.label_en?.trim() || null,
      type: f.type,
      required: f.required,
      sort_order: i,
    })),
    channels: e.channels.map((c, i) => ({
      key: c.key.trim(),
      label_ru: c.label_ru.trim(),
      label_en: c.label_en?.trim() || null,
      sort_order: i,
    })),
  }
}

async function onSave() {
  if (!editing.value || !canSave.value) return
  saving.value = true
  try {
    const payload = normalize()
    if (isNew.value) {
      const created = await createMutation.mutateAsync({
        slug: editing.value.slug.trim(),
        ...payload,
      })
      isNew.value = false
      selectedId.value = created.id
    } else {
      await updateMutation.mutateAsync({ id: editing.value.id!, dto: payload })
    }
    message.success(t('common.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!editing.value?.id) return
  deleting.value = true
  try {
    await deleteMutation.mutateAsync(editing.value.id)
    message.success(t('common.deleted'))
    editing.value = null
    selectedId.value = null
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.dir-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dir-settings__bar {
  display: flex;
  gap: 8px;
  align-items: center;
}
.dir-settings__select {
  flex: 1;
}
.empty-hint {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 12px;
  border: 1px dashed var(--n-border-color, #ddd);
  border-radius: 8px;
}
.row-2 {
  display: flex;
  gap: 12px;
}
.row-2 > * {
  flex: 1;
}
.section-divider {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
}
.schema-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 8px;
}
.schema-row__grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 110px auto;
  gap: 6px;
  align-items: center;
}
.schema-row__grid--channel {
  grid-template-columns: 1fr 1fr 1fr;
}
.add-row {
  margin-bottom: 8px;
}
.dir-settings__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.footer-spacer {
  flex: 1;
}
</style>
