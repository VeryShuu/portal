<template>
  <div style="display:flex;align-items:center;justify-content:center;min-height:100vh">
    <n-spin size="large" />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin } from 'naive-ui'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

onMounted(async () => {
  await auth.loadUser()
  router.replace('/')
})
</script>
