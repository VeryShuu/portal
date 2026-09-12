import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useManageDrawer(validKeys?: readonly string[]) {
  const route = useRoute()
  const router = useRouter()

  const active = computed<string | null>(() => {
    const v = route.query.manage
    if (typeof v !== 'string') return null
    if (validKeys && !validKeys.includes(v)) return null
    return v
  })

  function open(key: string) {
    if (route.query.manage === key) return
    router.replace({ query: { ...route.query, manage: key } })
  }

  function close() {
    if (route.query.manage == null) return
    const next = { ...route.query }
    delete next.manage
    router.replace({ query: next })
  }

  function is(key: string) {
    return active.value === key
  }

  return { active, open, close, is }
}
