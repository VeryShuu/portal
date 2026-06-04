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

        <n-form-item :label="t('directories.fields.folderUrl')">
          <n-input
            v-model:value="form.folder_url"
            placeholder="https://"
            clearable
          />
        </n-form-item>

        <template v-if="isEdit">
          <n-form-item :label="t('directories.fields.avatar')">
            <div class="avatar-row">
              <n-avatar
                :size="56"
                :src="form.avatar_path ?? undefined"
              >
                {{ avatarInitials }}
              </n-avatar>
              <n-upload
                :show-file-list="false"
                accept="image/*"
                :custom-request="onAvatarUpload"
              >
                <n-button
                  size="small"
                  :loading="avatarBusy"
                >
                  {{ t('directories.uploadAvatar') }}
                </n-button>
              </n-upload>
              <n-button
                v-if="form.avatar_path"
                size="small"
                quaternary
                :loading="avatarBusy"
                @click="onAvatarDelete"
              >
                {{ t('common.delete') }}
              </n-button>
            </div>
          </n-form-item>
        </template>

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
          <n-button
            size="small"
            quaternary
            circle
            class="contact-edit__del"
            @click="removeContact(idx)"
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
  NAvatar, NButton, NDivider, NDrawer, NDrawerContent, NForm, NFormItem,
  NIcon, NInput, NSelect, NUpload, useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import { AddOutline, TrashOutline } from '@vicons/ionicons5'
import type {
  ContactInput, DirectoryField, DirectoryPublic, EntryPublic,
} from '../../api/directories'
import { uploadEntryAvatar, deleteEntryAvatar } from '../../api/directories'
import {
  useCreateEntryMutation, useUpdateEntryMutation, useDeleteEntryMutation,
} from '../../queries/directories'

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
const avatarBusy = ref(false)

interface FormState {
  name: string
  folder_url: string
  avatar_path: string | null
  attributes: Record<string, string>
  note: string
  contacts: ContactInput[]
}

const form = reactive<FormState>({
  name: '',
  folder_url: '',
  avatar_path: null,
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

const avatarInitials = computed(() => {
  const name = form.name?.trim() ?? ''
  return name ? (name[0] ?? '?').toUpperCase() : '?'
})

function resetForm() {
  const e = props.entry
  form.name = e?.name ?? ''
  form.folder_url = e?.folder_url ?? ''
  form.avatar_path = e?.avatar_path ?? null
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
    folder_url: form.folder_url.trim() || null,
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

async function onAvatarUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if (!props.entry || !file.file) {
    onError()
    return
  }
  avatarBusy.value = true
  try {
    const updated = await uploadEntryAvatar(slug.value, props.entry.id, file.file)
    form.avatar_path = updated.avatar_path
    message.success(t('common.saved'))
    emit('saved')
    onFinish()
  } catch {
    message.error(t('errors.generic'))
    onError()
  } finally {
    avatarBusy.value = false
  }
}

async function onAvatarDelete() {
  if (!props.entry) return
  avatarBusy.value = true
  try {
    await deleteEntryAvatar(slug.value, props.entry.id)
    form.avatar_path = null
    emit('saved')
  } catch {
    message.error(t('errors.generic'))
  } finally {
    avatarBusy.value = false
  }
}
</script>

<style scoped>
.avatar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
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
.contact-edit__del {
  flex: 0 0 auto;
  margin-top: 2px;
}
.add-contact {
  margin-bottom: 8px;
}
.footer-spacer {
  flex: 1;
}
</style>
