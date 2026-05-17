<template>
  <div>
    <div class="tab-toolbar">
      <span class="hint">{{ t('admin.worldClock.hint') }}</span>
      <n-button
        style="margin-left:auto"
        @click="onReset"
      >
        {{ t('admin.worldClock.reset') }}
      </n-button>
      <n-button
        type="primary"
        @click="openAdd"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.worldClock.add') }}
      </n-button>
    </div>

    <div
      v-if="!cities.length"
      class="empty"
    >
      {{ t('admin.worldClock.empty') }}
    </div>

    <ul
      v-else
      ref="listRef"
      class="city-list"
    >
      <li
        v-for="city in cities"
        :key="city.id"
        :data-id="city.id"
        class="city-row"
      >
        <span
          class="drag-handle"
          :title="t('admin.worldClock.dragHint')"
        >
          <n-icon><ReorderThreeOutline /></n-icon>
        </span>
        <div class="city-row__main">
          <div class="city-row__name">
            {{ city.name }}
          </div>
          <div class="city-row__tz">
            {{ city.timezone }}
          </div>
        </div>
        <span class="city-row__time">{{ formatLocal(city.timezone) }}</span>
        <n-button
          size="small"
          quaternary
          circle
          :title="t('common.edit')"
          @click="openEdit(city)"
        >
          <template #icon>
            <n-icon><CreateOutline /></n-icon>
          </template>
        </n-button>
        <n-button
          size="small"
          quaternary
          circle
          type="error"
          :title="t('common.delete')"
          @click="onDelete(city)"
        >
          <template #icon>
            <n-icon><TrashOutline /></n-icon>
          </template>
        </n-button>
      </li>
    </ul>

    <n-modal
      v-model:show="modalOpen"
      :title="editing ? t('admin.worldClock.editTitle') : t('admin.worldClock.addTitle')"
      preset="card"
      style="width:440px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
      >
        <n-form-item
          :label="t('admin.worldClock.nameLabel')"
          path="name"
        >
          <n-input
            v-model:value="form.name"
            :placeholder="t('admin.worldClock.namePlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.worldClock.tzLabel')"
          path="timezone"
        >
          <n-select
            v-model:value="form.timezone"
            filterable
            tag
            :options="tzOptions"
            :placeholder="t('admin.worldClock.tzPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('admin.worldClock.coordsLabel')">
          <div class="coords-row">
            <n-input-number
              v-model:value="form.lat"
              :placeholder="t('admin.worldClock.latPlaceholder')"
              :precision="4"
              :min="-90"
              :max="90"
              :show-button="false"
              style="flex:1"
            />
            <n-input-number
              v-model:value="form.lon"
              :placeholder="t('admin.worldClock.lonPlaceholder')"
              :precision="4"
              :min="-180"
              :max="180"
              :show-button="false"
              style="flex:1"
            />
            <n-button
              :loading="geocoding"
              :disabled="!form.name.trim()"
              :title="t('admin.worldClock.geocodeHint')"
              @click="onGeocode"
            >
              <template #icon>
                <n-icon><LocationOutline /></n-icon>
              </template>
            </n-button>
          </div>
          <div class="coords-hint">
            {{ t('admin.worldClock.coordsHint') }}
          </div>
        </n-form-item>
        <div class="tz-preview">
          <span class="tz-preview__label">{{ t('admin.worldClock.preview') }}</span>
          <span class="tz-preview__value">{{ previewTime }}</span>
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="modalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
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
import { ref, computed, onBeforeUnmount, onMounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NIcon, NModal, NForm, NFormItem, NInput, NInputNumber, NSelect,
  useMessage, type SelectOption,
} from 'naive-ui'
import { AddOutline, TrashOutline, CreateOutline, ReorderThreeOutline, LocationOutline } from '@vicons/ionicons5'
import Sortable from 'sortablejs'
import { useConfirmDialog } from '../../../composables/useConfirmDialog'
import { useWorldClockCities, type ClockCity } from '../../../composables/useWorldClockCities'

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const { cities, add, update, remove, reset, reorder, isValidTimezone } = useWorldClockCities()

const modalOpen = ref(false)
const editing = ref<ClockCity | null>(null)
const formRef = ref()
const form = ref({ name: '', timezone: '', lat: null as number | null, lon: null as number | null })
const geocoding = ref(false)

const listRef = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null

const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  timer = setInterval(() => { now.value = new Date() }, 30_000)
  initSortable()
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  sortable?.destroy()
  sortable = null
})

watch(listRef, () => initSortable())

function initSortable() {
  sortable?.destroy()
  sortable = null
  if (!listRef.value) return
  sortable = Sortable.create(listRef.value, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    onEnd(evt) {
      const oldIdx = evt.oldIndex
      const newIdx = evt.newIndex
      if (oldIdx == null || newIdx == null || oldIdx === newIdx) return
      const next = [...cities.value]
      const [moved] = next.splice(oldIdx, 1)
      next.splice(newIdx, 0, moved)
      reorder(next)
      nextTick(() => initSortable())
    },
  })
}

const COMMON_TZ = [
  'Europe/Moscow', 'Europe/Kaliningrad', 'Europe/Samara',
  'Asia/Yekaterinburg', 'Asia/Omsk', 'Asia/Krasnoyarsk',
  'Asia/Irkutsk', 'Asia/Yakutsk', 'Asia/Vladivostok',
  'Asia/Magadan', 'Asia/Sakhalin', 'Asia/Kamchatka',
  'Asia/Seoul', 'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore',
  'Asia/Dubai', 'Asia/Almaty', 'Asia/Tashkent',
  'Europe/London', 'Europe/Berlin', 'Europe/Paris',
  'America/New_York', 'America/Los_Angeles', 'UTC',
]

const tzOptions = computed<SelectOption[]>(() =>
  COMMON_TZ.map(tz => ({ label: tz, value: tz })),
)

const rules = computed(() => ({
  name: [{ required: true, message: t('admin.worldClock.nameRequired'), trigger: 'blur' }],
  timezone: [
    { required: true, message: t('admin.worldClock.tzRequired'), trigger: 'blur' },
    {
      validator: (_r: unknown, value: string) => isValidTimezone(value),
      message: t('admin.worldClock.tzInvalid'),
      trigger: 'blur',
    },
  ],
}))

const previewTime = computed(() => {
  if (!form.value.timezone || !isValidTimezone(form.value.timezone)) return '—'
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      timeZone: form.value.timezone,
      hour: '2-digit', minute: '2-digit', weekday: 'short',
      hourCycle: 'h23',
    }).format(now.value)
  } catch {
    return '—'
  }
})

function formatLocal(tz: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).format(now.value)
  } catch {
    return '—'
  }
}

function openAdd() {
  editing.value = null
  form.value = { name: '', timezone: '', lat: null, lon: null }
  modalOpen.value = true
}

function openEdit(row: ClockCity) {
  editing.value = row
  form.value = {
    name: row.name,
    timezone: row.timezone,
    lat: row.lat ?? null,
    lon: row.lon ?? null,
  }
  modalOpen.value = true
}

async function onGeocode() {
  const q = form.value.name.trim()
  if (!q) return
  geocoding.value = true
  try {
    const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=1&language=ru&format=json`
    const res = await fetch(url)
    if (!res.ok) throw new Error('geocoding failed')
    const data = await res.json()
    const first = data?.results?.[0]
    if (!first) {
      message.warning(t('admin.worldClock.geocodeNotFound'))
      return
    }
    form.value.lat = Number(first.latitude)
    form.value.lon = Number(first.longitude)
    if (!form.value.timezone && first.timezone) {
      form.value.timezone = String(first.timezone)
    }
    message.success(t('admin.worldClock.geocodeOk'))
  } catch {
    message.error(t('admin.worldClock.geocodeError'))
  } finally {
    geocoding.value = false
  }
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const payload = {
    name: form.value.name.trim(),
    code: editing.value?.code ?? form.value.name.trim().slice(0, 3).toUpperCase(),
    timezone: form.value.timezone.trim(),
    lat: form.value.lat ?? undefined,
    lon: form.value.lon ?? undefined,
  }
  if (editing.value) {
    update(editing.value.id, payload)
    message.success(t('admin.worldClock.saved'))
  } else {
    add(payload)
    message.success(t('admin.worldClock.added'))
  }
  modalOpen.value = false
  nextTick(() => initSortable())
}

async function onDelete(row: ClockCity) {
  const ok = await confirm({
    title: t('admin.worldClock.confirmDelete', { name: row.name }),
    content: '',
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  remove(row.id)
  message.success(t('admin.worldClock.deleted'))
  nextTick(() => initSortable())
}

async function onReset() {
  const ok = await confirm({
    title: t('admin.worldClock.confirmReset'),
    content: t('admin.worldClock.confirmResetHint'),
    positiveText: t('admin.worldClock.reset'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  reset()
  message.success(t('admin.worldClock.resetDone'))
  nextTick(() => initSortable())
}
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
.city-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.city-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.city-row:hover {
  border-color: var(--color-brand-red);
}
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: var(--color-text-muted);
  cursor: grab;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.drag-handle:hover {
  background: var(--color-bg-muted);
  color: var(--color-text);
}
.drag-handle:active { cursor: grabbing; }
.city-row__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.city-row__name {
  font-weight: 600;
  color: var(--color-text);
  font-size: 14px;
}
.city-row__tz {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--color-text-muted);
}
.city-row__time {
  font-family: var(--font-mono, monospace);
  font-weight: 700;
  font-size: 15px;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
  min-width: 56px;
  text-align: right;
}
.sortable-ghost {
  opacity: 0.4;
  background: var(--color-bg-muted);
}
.sortable-chosen {
  box-shadow: var(--shadow-md);
}
.coords-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.coords-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 4px;
}
.tz-preview {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-bg-muted);
  border-radius: var(--radius-md);
  font-size: 13px;
}
.tz-preview__label { color: var(--color-text-muted); }
.tz-preview__value {
  font-family: var(--font-mono, monospace);
  font-weight: 700;
  color: var(--color-text);
}
</style>
