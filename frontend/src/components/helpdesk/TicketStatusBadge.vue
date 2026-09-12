<template>
  <n-tag
    :type="tagType"
    size="small"
    round
    :bordered="false"
  >
    {{ label }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTag } from 'naive-ui'
import type { HelpdeskStatus } from '../../api/helpdesk'

const props = defineProps<{ status: HelpdeskStatus }>()
const { t } = useI18n()

const tagType = computed<'default' | 'info' | 'success' | 'warning' | 'error'>(() => {
  switch (props.status) {
    case 'new': return 'info'
    case 'open': return 'info'
    case 'pending': return 'warning'
    case 'closed': return 'default'
    default: return 'default'
  }
})

const label = computed(() => t(`helpdesk.statuses.${props.status}`))
</script>
