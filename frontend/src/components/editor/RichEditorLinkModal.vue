<template>
  <n-modal
    v-model:show="show"
    preset="dialog"
    :title="title"
    style="max-width: 480px"
  >
    <n-tabs
      v-model:value="tab"
      type="line"
      size="small"
      animated
    >
      <n-tab-pane
        name="url"
        :tab="t('editor.link.tabUrl')"
      >
        <div class="link-form">
          <div class="link-field">
            <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
            <label
              class="link-label"
              for="link-url-input"
            >{{ t('editor.link.url') }}</label>
            <n-input
              v-model:value="url"
              :placeholder="t('editor.link.urlPlaceholder')"
              :status="urlStatus"
              :input-props="{ id: 'link-url-input' }"
              clearable
              @update:value="onUrlChange"
            />
            <div
              v-if="urlError"
              class="link-error"
            >
              {{ urlError }}
            </div>
            <div
              v-else-if="url && isInternalKbLink(url)"
              class="link-hint"
            >
              {{ t('editor.link.kbInternalHint') }}
            </div>
          </div>

          <div
            v-if="showTextField"
            class="link-field"
          >
            <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
            <label
              class="link-label"
              for="link-text-input"
            >{{ t('editor.link.text') }}</label>
            <n-input
              v-model:value="text"
              :placeholder="t('editor.link.textPlaceholder')"
              :input-props="{ id: 'link-text-input' }"
              clearable
            />
          </div>

          <n-checkbox v-model:checked="newTab">
            {{ t('editor.link.newTab') }}
          </n-checkbox>
          <n-checkbox v-model:checked="nofollow">
            {{ t('editor.link.nofollow') }}
          </n-checkbox>
        </div>
      </n-tab-pane>
      <n-tab-pane
        name="kb"
        :tab="t('editor.link.tabKb')"
      >
        <div class="link-form">
          <div class="link-field">
            <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
            <label
              class="link-label"
              for="link-kb-search"
            >{{ t('editor.link.kbSearchLabel') }}</label>
            <n-input
              :value="kbQuery"
              :placeholder="t('editor.link.kbSearchPlaceholder')"
              :input-props="{ id: 'link-kb-search', autocomplete: 'off' }"
              clearable
              @update:value="onKbSearchInput"
              @keydown="onKbKeydown"
            />
          </div>
          <div
            v-if="kbLoading"
            class="kb-search-hint"
          >
            {{ t('common.loading') }}
          </div>
          <div
            v-else-if="kbQuery.trim().length >= kbMinLength && !kbResults.length"
            class="kb-search-hint"
          >
            {{ t('editor.link.kbNoResults') }}
          </div>
          <ul
            v-else-if="kbResults.length"
            class="kb-search-results"
            role="listbox"
          >
            <li
              v-for="(item, idx) in kbResults"
              :key="item.id"
              role="option"
              :aria-selected="idx === kbActiveIndex"
            >
              <button
                type="button"
                class="kb-search-item"
                :class="{ 'is-active': idx === kbActiveIndex }"
                @click="selectKbArticle(item)"
                @mouseenter="kbActiveIndex = idx"
                @focusin="kbActiveIndex = idx"
              >
                <span class="kb-search-item-title">
                  <template
                    v-for="(chunk, ci) in highlightKbMatch(item.title)"
                    :key="ci"
                  >
                    <mark
                      v-if="chunk.match"
                      class="kb-search-item-hl"
                    >{{ chunk.text }}</mark>
                    <span v-else>{{ chunk.text }}</span>
                  </template>
                </span>
                <span
                  v-if="item.status && item.status !== 'published'"
                  class="kb-search-item-status"
                >{{ item.status }}</span>
              </button>
            </li>
          </ul>
          <div
            v-else
            class="kb-search-hint"
          >
            {{ t('editor.link.kbHint', { n: kbMinLength }) }}
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>
    <template #action>
      <n-button
        v-if="editingExisting"
        size="small"
        type="error"
        ghost
        @click="$emit('remove')"
      >
        {{ t('editor.link.remove') }}
      </n-button>
      <n-button
        size="small"
        @click="show = false"
      >
        {{ t('common.cancel') }}
      </n-button>
      <n-button
        size="small"
        type="primary"
        :disabled="!canSubmit"
        @click="$emit('submit')"
      >
        {{ editingExisting ? t('editor.link.update') : t('editor.insert') }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { NButton, NCheckbox, NInput, NModal, NTabs, NTabPane } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import type { KbArticleListItem } from '@/api/kb'
import type { LinkDialogTab } from './useEditorLinkDialog'

const show = defineModel<boolean>('show', { required: true })
const tab = defineModel<LinkDialogTab>('tab', { required: true })
const kbActiveIndex = defineModel<number>('kbActiveIndex', { required: true })
const url = defineModel<string>('url', { required: true })
const text = defineModel<string>('text', { required: true })
const newTab = defineModel<boolean>('newTab', { required: true })
const nofollow = defineModel<boolean>('nofollow', { required: true })

defineProps<{
  title: string
  urlStatus: 'error' | undefined
  urlError: string
  showTextField: boolean
  editingExisting: boolean
  canSubmit: boolean
  kbQuery: string
  kbLoading: boolean
  kbMinLength: number
  kbResults: KbArticleListItem[]
  onUrlChange: (value: string) => void
  isInternalKbLink: (url: string) => boolean
  onKbSearchInput: (value: string) => void
  onKbKeydown: (event: KeyboardEvent) => void
  selectKbArticle: (item: KbArticleListItem) => void
  highlightKbMatch: (title: string) => Array<{ text: string; match: boolean }>
}>()

defineEmits<{
  remove: []
  submit: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.link-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
.link-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.link-label {
  font-size: 13px;
  color: var(--n-text-color-2, #666);
}
.link-error {
  font-size: 12px;
  color: var(--n-error-color, #d03050);
}
.link-hint {
  font-size: 12px;
  color: var(--n-text-color-3, #888);
}
.kb-search-hint {
  font-size: 13px;
  color: var(--n-text-color-3, #888);
  padding: 6px 2px;
}
.kb-search-results {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 4px;
}
.kb-search-results li {
  border-bottom: 1px solid var(--n-border-color, #f0f0f3);
}
.kb-search-results li:last-child {
  border-bottom: none;
}
.kb-search-item {
  width: 100%;
  text-align: left;
  background: transparent;
  border: none;
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font: inherit;
  color: inherit;
}
.kb-search-item:hover,
.kb-search-item:focus-visible,
.kb-search-item.is-active {
  background: var(--n-table-header-color, #f5f5f7);
  outline: none;
}
.kb-search-item-hl {
  background: #fff3a0;
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
}
.kb-search-item-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-search-item-status {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--n-text-color-3, #999);
  text-transform: uppercase;
}
</style>
