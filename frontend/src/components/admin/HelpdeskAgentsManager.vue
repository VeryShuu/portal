<template>
  <div class="helpdesk-agents">
    <!-- Добавление агента: remote-search по пользователям -->
    <div class="helpdesk-agents__add">
      <n-select
        :value="null"
        filterable
        remote
        clearable
        :placeholder="t('admin.helpdesk.agents.searchPlaceholder')"
        :loading="searching"
        :options="searchOptions"
        :consistent-menu-width="false"
        @search="onSearch"
        @update:value="onPickUser"
      />
    </div>

    <!-- Список агентов -->
    <n-spin :show="isLoading">
      <n-empty
        v-if="!isLoading && agents.length === 0"
        :description="t('admin.helpdesk.agents.empty')"
        style="margin: 24px 0"
      />
      <div
        v-for="agent in agents"
        :key="agent.user_id"
        class="helpdesk-agent-row"
      >
        <div class="helpdesk-agent-row__main">
          <div class="helpdesk-agent-row__name">
            {{ agent.user_name ?? agent.user_email ?? agent.user_id }}
          </div>
          <div class="helpdesk-agent-row__email">
            {{ agent.user_email }}
          </div>
        </div>
        <div class="helpdesk-agent-row__actions">
          <n-tooltip>
            <template #trigger>
              <n-switch
                :value="agent.notify_new"
                :loading="togglingId === agent.user_id"
                size="small"
                @update:value="(v: boolean) => onToggleNotify(agent, v)"
              />
            </template>
            {{ t('admin.helpdesk.agents.notifyNewHint') }}
          </n-tooltip>
          <n-button
            quaternary
            type="error"
            size="small"
            :loading="deletingId === agent.user_id"
            @click="onDelete(agent)"
          >
            {{ t('common.delete') }}
          </n-button>
        </div>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, useDialog, NSpin, NEmpty, NSelect, NSwitch, NButton, NTooltip } from 'naive-ui'
import { fetchUsers, type UserPublic } from '../../api/users'
import type { HelpdeskAgent } from '../../api/helpdesk'
import { useHelpdeskAgentsQuery, useAddHelpdeskAgentMutation, useUpdateHelpdeskAgentMutation, useDeleteHelpdeskAgentMutation } from '../../queries/helpdesk'
import { useDebounceFn } from '../../composables/useDebounceFn'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()
const dialog = useDialog()

const { data, isLoading } = useHelpdeskAgentsQuery()
const addMut = useAddHelpdeskAgentMutation()
const updateMut = useUpdateHelpdeskAgentMutation()
const deleteMut = useDeleteHelpdeskAgentMutation()

const agents = computed<HelpdeskAgent[]>(() => data.value?.items ?? [])

// ── Remote search ────────────────────────────────────────────────────────
const searching = ref(false)
const searchOptions = ref<{ label: string; value: string }[]>([])
const MIN_CHARS = 2

async function doSearch(q: string) {
  if (!q || q.trim().length < MIN_CHARS) {
    searchOptions.value = []
    return
  }
  searching.value = true
  try {
    const res = await fetchUsers({ q: q.trim(), page_size: 20 })
    searchOptions.value = res.items.map((u: UserPublic) => ({
      label: `${u.full_name} (${u.email})`,
      value: u.id,
    }))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    searching.value = false
  }
}
const onSearch = useDebounceFn(doSearch, 300)

async function onPickUser(userId: string | null) {
  if (!userId) return
  try {
    await addMut.mutateAsync({ user_id: userId, notify_new: true })
    message.success(t('admin.helpdesk.agents.added'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

// ── Toggle notify_new ────────────────────────────────────────────────────
const togglingId = ref<string | null>(null)
async function onToggleNotify(agent: HelpdeskAgent, value: boolean) {
  togglingId.value = agent.user_id
  try {
    await updateMut.mutateAsync({
      userId: agent.user_id,
      dto: { user_id: agent.user_id, notify_new: value },
    })
    message.success(t('admin.modules.saved'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    togglingId.value = null
  }
}

// ── Delete ───────────────────────────────────────────────────────────────
const deletingId = ref<string | null>(null)
function onDelete(agent: HelpdeskAgent) {
  dialog.warning({
    title: t('common.confirm'),
    content: t('admin.helpdesk.agents.deleteConfirm', {
      name: agent.user_name ?? agent.user_email ?? agent.user_id,
    }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      deletingId.value = agent.user_id
      try {
        await deleteMut.mutateAsync(agent.user_id)
        message.success(t('admin.helpdesk.agents.deleted'))
      } catch (e) {
        message.error(parseApiError(e, t))
      } finally {
        deletingId.value = null
      }
    },
  })
}
</script>

<style scoped>
.helpdesk-agents__add {
  margin-bottom: 16px;
}
.helpdesk-agent-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.09));
}
.helpdesk-agent-row:last-child {
  border-bottom: none;
}
.helpdesk-agent-row__main {
  min-width: 0;
}
.helpdesk-agent-row__name {
  font-weight: 500;
}
.helpdesk-agent-row__email {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.helpdesk-agent-row__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
