<template>
  <n-drawer
    :show="show"
    :width="560"
    placement="right"
    @update:show="(v: boolean) => { if (!v) emit('close') }"
  >
    <n-drawer-content
      :title="isEdit ? t('directories.editEntry') : t('directories.addEntry')"
      closable
    >
      <n-form
        label-placement="top"
        @submit.prevent
      >
        <n-form-item
          :label="t('directories.fields.name')"
          required
        >
          <n-input
            v-model:value="form.name"
            :placeholder="t('directories.fields.namePlaceholder')"
          />
        </n-form-item>

        <n-form-item :label="t('directories.fields.folder')">
          <n-tree-select
            v-model:value="form.folder_id"
            :options="folderOptions"
            :placeholder="t('directories.fields.folderPlaceholder')"
            :loading="folderTreeLoading"
            clearable
            filterable
            key-field="key"
            label-field="label"
            children-field="children"
          />
        </n-form-item>

        <n-divider class="section-divider">
          {{ t('directories.attributes') }}
        </n-divider>
        <div
          v-if="!sortedFields.length"
          class="empty-hint"
        >
          {{ t('directories.noFields') }}
        </div>
        <n-form-item
          v-for="f in sortedFields"
          :key="f.key"
          :label="fieldLabel(f)"
          :required="f.required"
        >
          <n-input
            v-if="f.type === 'multiline'"
            v-model:value="form.attributes[f.key]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
          />
          <n-input
            v-else
            v-model:value="form.attributes[f.key]"
            :placeholder="fieldLabel(f)"
          />
        </n-form-item>

        <n-divider class="section-divider">
          {{ t('directories.contacts') }}
        </n-divider>
        <div
          v-if="!form.contacts.length"
          class="empty-hint"
        >
          {{ t('directories.noContacts') }}
        </div>
        <div
          v-for="(c, idx) in form.contacts"
          :key="idx"
          class="contact-edit"
        >
          <div class="contact-edit__grid">
            <n-input
              v-model:value="c.role"
              size="small"
              :placeholder="t('directories.contact.role')"
            />
            <n-select
              v-model:value="c.channel"
              size="small"
              :options="channelOptions"
              :placeholder="t('directories.contact.channel')"
            />
            <n-input
              v-model:value="c.value"
              size="small"
              :placeholder="t('directories.contact.value')"
            />
            <n-input
              v-model:value="c.label"
              size="small"
              :placeholder="t('directories.contact.label')"
            />
          </div>
          <div class="contact-edit__actions">
            <n-button
              size="small"
              quaternary
              circle
              :disabled="idx === 0"
              :title="t('directories.contact.moveUp')"
              @click="moveContact(idx, -1)"
            >
              <template #icon>
                <n-icon><ChevronUpOutline /></n-icon>
              </template>
            </n-button>
            <n-button
              size="small"
              quaternary
              circle
              :disabled="idx === form.contacts.length - 1"
              :title="t('directories.contact.moveDown')"
              @click="moveContact(idx, 1)"
            >
              <template #icon>
                <n-icon><ChevronDownOutline /></n-icon>
              </template>
            </n-button>
            <n-button
              size="small"
              quaternary
              circle
              @click="removeContact(idx)"
            >
              <template #icon>
                <n-icon><TrashOutline /></n-icon>
              </template>
            </n-button>
          </div>
        </div>
        <n-button
          size="small"
          dashed
          block
          class="add-contact"
          @click="addContact"
        >
          <template #icon>
            <n-icon><AddOutline /></n-icon>
          </template>
          {{ t('directories.addContact') }}
        </n-button>

        <n-divider class="section-divider">
          {{ t('directories.fields.note') }}
        </n-divider>
        <n-form-item :show-label="false">
          <n-input
            v-model:value="form.note"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
          />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-button
          v-if="isEdit"
          quaternary
          type="error"
          :loading="deleting"
          @click="onDelete"
        >
          {{ t('common.delete') }}
        </n-button>
        <div class="footer-spacer" />
        <n-button @click="emit('close')">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="!form.name.trim()"
          @click="onSubmit"
        >
          {{ t('common.save') }}
        </n-button>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NDivider, NDrawer, NDrawerContent, NForm, NFormItem,
  NIcon, NInput, NSelect, NTreeSelect, useMessage,
} from 'naive-ui'
import {
  AddOutline, ChevronDownOutline, ChevronUpOutline, TrashOutline,
} from '@vicons/ionicons5'
import type {
  ContactInput, DirectoryField, DirectoryPublic, EntryPublic,
} from '../../api/directories'
import type { FileFolderTreeNode } from '../../api/files'
import {
  useCreateEntryMutation, useUpdateEntryMutation, useDeleteEntryMutation,
} from '../../queries/directories'
import { useFolderTreeQuery } from '../../queries/files'

interface FolderOption {
  key: string
  label: string
  children?: FolderOption[]
  [k: string]: unknown
}

const props = defineProps<{
  show: boolean
  directory: DirectoryPublic
  entry?: EntryPublic | null
  lang?: 'ru' | 'en'
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const { t } = useI18n()
const message = useMessage()

const slug = computed(() => props.directory.slug)
const isEdit = computed(() => !!props.entry)

const createMutation = useCreateEntryMutation(slug)
const updateMutation = useUpdateEntryMutation(slug)
const deleteMutation = useDeleteEntryMutation(slug)

const saving = ref(false)
const deleting = ref(false)

const folderTree = useFolderTreeQuery()
const folderTreeLoading = computed(() => folderTree.isLoading.value)

function mapFolderNodes(nodes: FileFolderTreeNode[]): FolderOption[] {
  return nodes.map((n) => ({
    key: n.id,
    label: n.name,
    children: n.children.length ? mapFolderNodes(n.children) : undefined,
  }))
}

const folderOptions = computed<FolderOption[]>(() =>
  mapFolderNodes(folderTree.data.value?.items ?? []),
)

interface FormState {
  name: string
  folder_id: string | null
  attributes: Record<string, string>
  note: string
  contacts: ContactInput[]
}

const form = reactive<FormState>({
  name: '',
  folder_id: null,
  attributes: {},
  note: '',
  contacts: [],
})

const sortedFields = computed(() =>
  [...props.directory.field_schema].sort((a, b) => a.sort_order - b.sort_order),
)

const channelOptions = computed(() =>
  [...props.directory.channels]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((c) => ({
      label: props.lang === 'en' && c.label_en ? c.label_en : c.label_ru,
      value: c.key,
    })),
)

function fieldLabel(f: DirectoryField): string {
  return props.lang === 'en' && f.label_en ? f.label_en : f.label_ru
}

function resetForm() {
  const e = props.entry
  form.name = e?.name ?? ''
  form.folder_id = e?.folder_id ?? null
  form.note = e?.note ?? ''
  const attrs: Record<string, string> = {}
  for (const f of props.directory.field_schema) {
    attrs[f.key] = e?.attributes?.[f.key] ?? ''
  }
  form.attributes = attrs
  form.contacts = (e?.contacts ?? []).map((c) => ({
    role: c.role ?? '',
    channel: c.channel,
    label: c.label ?? '',
    value: c.value,
    sort_order: c.sort_order,
  }))
}

watch(
  () => [props.show, props.entry?.id] as const,
  ([show]) => {
    if (show) resetForm()
  },
  { immediate: true },
)

function addContact() {
  form.contacts.push({
    role: '',
    channel: props.directory.channels[0]?.key ?? '',
    label: '',
    value: '',
    sort_order: form.contacts.length,
  })
}

function removeContact(idx: number) {
  form.contacts.splice(idx, 1)
}

function moveContact(idx: number, delta: number) {
  const target = idx + delta
  if (target < 0 || target >= form.contacts.length) return
  const [moved] = form.contacts.splice(idx, 1)
  form.contacts.splice(target, 0, moved)
}

function buildPayload() {
  const attributes: Record<string, string> = {}
  for (const [k, v] of Object.entries(form.attributes)) {
    if (v && v.trim()) attributes[k] = v.trim()
  }
  const contacts: ContactInput[] = form.contacts
    .filter((c) => c.value && c.value.trim() && c.channel)
    .map((c, i) => ({
      role: c.role?.trim() || null,
      channel: c.channel,
      label: c.label?.trim() || null,
      value: c.value.trim(),
      sort_order: i,
    }))
  return {
    name: form.name.trim(),
    folder_id: form.folder_id,
    attributes,
    note: form.note.trim() || null,
    contacts,
  }
}

async function onSubmit() {
  if (!form.name.trim()) return
  saving.value = true
  try {
    const payload = buildPayload()
    if (props.entry) {
      await updateMutation.mutateAsync({ id: props.entry.id, dto: payload })
    } else {
      await createMutation.mutateAsync(payload)
    }
    message.success(t('common.saved'))
    emit('saved')
    emit('close')
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!props.entry) return
  deleting.value = true
  try {
    await deleteMutation.mutateAsync(props.entry.id)
    message.success(t('common.deleted'))
    emit('saved')
    emit('close')
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.section-divider {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
}
.empty-hint {
  font-size: 12.5px;
  color: var(--color-text-muted);
  margin-bottom: 10px;
}
.contact-edit {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 10px;
}
.contact-edit__grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.contact-edit__actions {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 2px;
}
.add-contact {
  margin-bottom: 8px;
}
.footer-spacer {
  flex: 1;
}
</style>
