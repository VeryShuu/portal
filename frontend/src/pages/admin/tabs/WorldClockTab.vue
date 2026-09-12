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
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NIcon, NModal, NForm, NFormItem, NInput, NInputNumber, NSelect,
} from 'naive-ui'
import { AddOutline, TrashOutline, CreateOutline, ReorderThreeOutline, LocationOutline } from '@vicons/ionicons5'
import { useWorldClockCities } from '../../../composables/useWorldClockCities'
import { useWorldClockClock } from '../../../composables/useWorldClockClock'
import { useWorldClockSortable } from '../../../composables/useWorldClockSortable'
import { useWorldClockForm } from '../../../composables/useWorldClockForm'

const { t } = useI18n()
const { cities, add, update, remove, reset, reorder, isValidTimezone } = useWorldClockCities()

const { now, formatLocal } = useWorldClockClock()

const { listRef, initSortable } = useWorldClockSortable(cities, reorder)

const {
  modalOpen, editing, formRef, form, geocoding,
  tzOptions, rules, previewTime,
  openAdd, openEdit, onGeocode, submit, onDelete, onReset,
} = useWorldClockForm({
  now,
  cities,
  add,
  update,
  remove,
  reset,
  reorder,
  isValidTimezone,
  onAfterMutation: () => initSortable(),
})

onMounted(() => {
  initSortable()
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
