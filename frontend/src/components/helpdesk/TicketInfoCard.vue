<template>
  <n-card
    class="ticket-info"
    size="small"
    :bordered="true"
  >
    <template #header>
      <span class="ticket-info__title">{{ t('helpdesk.info.title') }}</span>
    </template>

    <dl class="ticket-info__fields">
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.columnState') }}
        </dt>
        <dd class="ticket-info__value ticket-info__value--badge">
          <TicketStatusBadge :status="ticket.status" />
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.source') }}
        </dt>
        <dd class="ticket-info__value">
          {{ t(`helpdesk.sources.${ticket.source}`) }}
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.assignee') }}
        </dt>
        <dd class="ticket-info__value">
          <!-- Read-only вид: для заявителя (``HelpdeskMyTicketDetailPage``) и
               для агента, когда нет прав/нет активных агентов. -->
          <span
            v-if="!editable"
            class="ticket-info__assignee-readonly"
          >
            {{ ticket.assignee_name ?? t('helpdesk.unassigned') }}
          </span>

          <!-- Editable вид: кликабельное поле открывает popover с n-select
               активных helpdesk-агентов. Только на странице агента. -->
          <n-popover
            v-else
            trigger="click"
            placement="bottom-start"
            :width="280"
            :show="popoverShown"
            @update:show="onPopoverToggle"
          >
            <template #trigger>
              <button
                type="button"
                class="ticket-info__assignee-trigger"
                :aria-label="t('helpdesk.assigneeChange')"
              >
                <span class="ticket-info__assignee-name">
                  {{ ticket.assignee_name ?? t('helpdesk.unassigned') }}
                </span>
                <n-icon
                  size="14"
                  class="ticket-info__assignee-icon"
                >
                  <component :is="ChevronDown" />
                </n-icon>
              </button>
            </template>

            <div class="ticket-info__assignee-popover">
              <div class="ticket-info__assignee-popover-title">
                {{ t('helpdesk.assigneeChange') }}
              </div>
              <!-- Простой список активных агентов: для ~5 человек поиск избыточен.
                   Клик по строке сразу применяет смену (без отдельной кнопки Apply).
                   Текущий assignee помечен и отключён (no-op). -->
              <ul
                v-if="!agentsLoading && agentOptions.length > 0"
                class="ticket-info__assignee-list"
              >
                <li
                  v-for="agent in agentOptions"
                  :key="agent.user_id"
                >
                  <button
                    type="button"
                    class="ticket-info__assignee-option"
                    :class="{
                      'ticket-info__assignee-option--current': agent.is_current,
                      'ticket-info__assignee-option--me': agent.is_me,
                    }"
                    :disabled="assigning || agent.is_current"
                    :aria-current="agent.is_current ? 'true' : undefined"
                    @click="applyAssignee(agent.user_id)"
                  >
                    <span class="ticket-info__assignee-option-name">
                      {{ agent.label }}
                    </span>
                    <span
                      v-if="agent.is_current"
                      class="ticket-info__assignee-option-check"
                      aria-hidden="true"
                    >
                      ✓
                    </span>
                  </button>
                </li>
              </ul>
              <div
                v-else-if="agentsLoading"
                class="ticket-info__assignee-empty"
              >
                {{ t('common.loading') }}
              </div>
              <div
                v-else
                class="ticket-info__assignee-empty"
              >
                {{ t('helpdesk.assigneeEmpty') }}
              </div>
            </div>
          </n-popover>
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.created') }}
        </dt>
        <dd class="ticket-info__value">
          {{ formatDate(ticket.created_at) }}
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.lastActivity') }}
        </dt>
        <dd class="ticket-info__value">
          {{ formatDate(ticket.last_activity_at) }}
        </dd>
      </div>
    </dl>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NCard, NIcon, NPopover, useMessage } from 'naive-ui'
import { ChevronDown } from '@vicons/ionicons5'
import TicketStatusBadge from './TicketStatusBadge.vue'
import type { HelpdeskTicketDetail } from '../../api/helpdesk'
import { useAssignableAgentsQuery, useAssignTicketMutation } from '../../queries/helpdesk'
import { parseApiError } from '../../utils/parseApiError'
import { useAuthStore } from '../../stores/auth'

const props = withDefaults(defineProps<{ ticket: HelpdeskTicketDetail; editable?: boolean }>(), {
  editable: false,
})
const { t, locale } = useI18n()
const message = useMessage()
const auth = useAuthStore()

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Assignee editing (только для агента, editable=true) ──────────────────────
// Popover с простым списком активных helpdesk-агентов. Список подгружается лениво
// при первом открытии popover'а (query активируется только когда popover открыт),
// чтобы не гонять запрос на каждой карточке тикета — большая часть агентов
// открывает карточку чтобы ответить, а не сменить ответственного. Поиск не нужен:
// агентов поддержки обычно ~5 человек — проще показать списком, клик сразу
// применяет смену (без отдельной кнопки Apply).

const popoverShown = ref(false)
const assigning = ref(false)

// Запрос активируется только при открытом popover (``enabled``). staleTime 60 c
// в query — повторные открытия в течение минуты берут кеш.
const agentsQuery = useAssignableAgentsQuery(popoverShown)
const agentsLoading = computed(() => agentsQuery.isLoading.value)

// Текущий агент — для суффикса «(вы)» в строке списка.
const currentUserId = computed(() => auth.user?.id ?? null)

interface AssigneeOption {
  user_id: string
  label: string
  is_current: boolean
  is_me: boolean
}

const agentOptions = computed<AssigneeOption[]>(() => {
  const items = agentsQuery.data.value?.items ?? []
  return items.map((agent) => {
    const isMe = currentUserId.value !== null && agent.user_id === currentUserId.value
    const name = agent.full_name ?? agent.email
    const label = isMe ? `${name} ${t('helpdesk.assigneeSelfHint')}` : name
    return {
      user_id: agent.user_id,
      label,
      is_current: agent.user_id === props.ticket.assignee_user_id,
      is_me: isMe,
    }
  })
})

const assignMutation = useAssignTicketMutation(props.ticket.id)

function onPopoverToggle(shown: boolean) {
  popoverShown.value = shown
}

async function applyAssignee(targetUserId: string) {
  // No-op: клик по текущему assignee (кнопка disabled, но страховка на случай
  // рассинхрона между списком и ticket.assignee_user_id).
  if (targetUserId === props.ticket.assignee_user_id) return
  if (assigning.value) return
  assigning.value = true
  try {
    await assignMutation.mutateAsync(targetUserId)
    message.success(t('helpdesk.assigneeChanged'))
    popoverShown.value = false
  } catch (e) {
    // 404 «Agent not found» — типичный кейс: список агентов устарел (кто-то
    // уволен/убран из helpdesk_agents за время открытой карточки). Инвалидируем
    // кеш, чтобы при повторном открытии подтянулся свежий список.
    message.error(parseApiError(e, t))
    agentsQuery.refetch()
  } finally {
    assigning.value = false
  }
}
</script>

<style scoped>
/* Карточка служебных полей тикета в правом сайдбаре (над профилем заявителя). */
.ticket-info__title {
  font-size: 13px;
  font-weight: 600;
}
.ticket-info__fields {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ticket-info__row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.ticket-info__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  font-weight: 600;
  margin: 0;
}
.ticket-info__value {
  margin: 0;
  font-size: 13px;
  color: var(--color-text);
  word-break: break-word;
}
.ticket-info__value--badge {
  line-height: 1.8;
}

/* Кликабельный триггер смены ответственного (только editable-режим). */
.ticket-info__assignee-readonly {
  /* Заполнитель для read-only вида — просто текст, без интерактива. */
}
.ticket-info__assignee-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  margin: -2px -6px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--color-text);
  font: inherit;
  font-size: 13px;
  border-radius: 4px;
  transition: background-color 0.15s ease;
}
.ticket-info__assignee-trigger:hover {
  background: var(--color-hover-bg, rgba(0, 0, 0, 0.05));
}
.ticket-info__assignee-trigger:focus-visible {
  outline: 2px solid var(--color-brand, #18a058);
  outline-offset: 1px;
}
.ticket-info__assignee-icon {
  color: var(--color-text-muted);
  flex-shrink: 0;
}

/* Содержимое popover'а смены ответственного. */
.ticket-info__assignee-popover {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;
  min-width: 220px;
}
.ticket-info__assignee-popover-title {
  font-size: 13px;
  font-weight: 600;
  padding: 0 4px 4px;
}

/* Простой список активных агентов (без поиска — для ~5 человек избыточно). */
.ticket-info__assignee-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.ticket-info__assignee-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--color-text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  border-radius: 4px;
  transition: background-color 0.12s ease;
}
.ticket-info__assignee-option:hover:not(:disabled) {
  background: var(--color-hover-bg, rgba(0, 0, 0, 0.05));
}
.ticket-info__assignee-option:focus-visible {
  outline: 2px solid var(--color-brand, #18a058);
  outline-offset: -2px;
}
.ticket-info__assignee-option:disabled {
  cursor: default;
  opacity: 0.6;
}
.ticket-info__assignee-option--current {
  font-weight: 600;
}
.ticket-info__assignee-option-check {
  color: var(--color-brand, #18a058);
  font-size: 14px;
  flex-shrink: 0;
}
.ticket-info__assignee-empty {
  padding: 8px 10px;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
