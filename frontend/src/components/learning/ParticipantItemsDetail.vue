<template>
  <div class="pitems">
    <n-spin
      :show="query.isLoading.value"
      size="small"
    >
      <n-empty
        v-if="query.data.value && query.data.value.items.length === 0"
        :description="t('learning.participants.noItems')"
        size="small"
        class="pitems__empty"
      />
      <div
        v-for="item in query.data.value?.items ?? []"
        :key="item.item_id"
        class="pitems__row"
      >
        <n-icon
          :size="16"
          aria-hidden="true"
        >
          <DocumentOutline v-if="item.type === 'material'" />
          <HelpCircleOutline v-else />
        </n-icon>
        <span class="pitems__title">{{ item.title }}</span>
        <n-tag
          size="tiny"
          :bordered="false"
          :type="item.completed ? 'success' : 'warning'"
        >
          {{ statusLabel(item) }}
        </n-tag>
        <span
          v-if="item.type === 'test'"
          class="pitems__attempts"
        >
          {{ t('learning.participants.attemptsCount', { count: item.attempts_submitted }) }}
        </span>
        <n-popconfirm
          v-if="item.type === 'test'"
          @positive-click="reset(item)"
        >
          <template #trigger>
            <n-button
              size="tiny"
              type="warning"
              quaternary
              :loading="resetMut.isPending.value && resetting === item.item_id"
            >
              {{ t('learning.participants.resetAttempts') }}
            </n-button>
          </template>
          {{ t('learning.participants.resetConfirm') }}
        </n-popconfirm>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NEmpty,
  NIcon,
  NPopconfirm,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { DocumentOutline, HelpCircleOutline } from '@vicons/ionicons5'
import {
  useParticipantItemsQuery,
  useResetParticipantAttemptsMutation,
} from '../../queries/learning'
import type { LearningParticipantItemStatus } from '../../api/learning'
import { parseApiError } from '../../utils/parseApiError'

/**
 * Детализация «как решён курс» (раскрываемая строка панели участников):
 * статус каждого элемента + число отправленных попыток у теста, сброс попыток.
 * Монтируется только при раскрытии строки — запрос ходит лениво.
 */
const props = defineProps<{ courseId: string; participantId: string }>()
const { t } = useI18n()
const message = useMessage()

const query = useParticipantItemsQuery(props.courseId, props.participantId, true)
const resetMut = useResetParticipantAttemptsMutation()
const resetting = ref<string | null>(null)

function statusLabel(item: LearningParticipantItemStatus): string {
  if (item.type === 'material') {
    return item.completed
      ? t('learning.participants.itemReviewed')
      : t('learning.participants.itemNotDone')
  }
  return item.test_passed
    ? t('learning.participants.itemDone')
    : t('learning.participants.itemNotDone')
}

async function reset(item: LearningParticipantItemStatus) {
  resetting.value = item.item_id
  try {
    const result = await resetMut.mutateAsync({
      courseId: props.courseId,
      participantId: props.participantId,
      itemId: item.item_id,
    })
    message.success(t('learning.participants.resetDone', { count: result.deleted_attempts }))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    resetting.value = null
  }
}
</script>

<style scoped>
.pitems {
  padding: 4px 0 8px 24px;
}

.pitems__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--color-border, #eee);
}

.pitems__row:last-child {
  border-bottom: 0;
}

.pitems__title {
  min-width: 0;
  font-weight: 550;
  overflow-wrap: anywhere;
}

.pitems__attempts {
  color: var(--color-text-muted, #999);
  font-size: 12px;
}

.pitems__empty {
  padding: 8px 0;
}
</style>
