<template>
  <form class="login" @submit.prevent="submit">
    <h1>{{ $t('auth.loginTitle') }}</h1>
    <input v-model="email" type="email" :placeholder="$t('auth.email')" required />
    <input v-model="password" type="password" :placeholder="$t('auth.password')" required />
    <p v-if="error" class="err">{{ $t('auth.invalidCredentials') }}</p>
    <button :disabled="busy">{{ $t('auth.login') }}</button>
  </form>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/stores/auth'

const email = ref('')
const password = ref('')
const error = ref(false)
const busy = ref(false)

const route = useRoute()
const router = useRouter()
const auth = useAuth()

async function submit() {
  busy.value = true
  error.value = false
  try {
    await auth.login(email.value, password.value)
    const redirect = route.query.redirect
    const target = typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/'
    router.replace(target)
  } catch {
    error.value = true
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login {
  display: flex;
  flex-direction: column;
  max-width: 360px;
  margin: 10vh auto;
  gap: 0.75rem;
  padding: 2rem;
}
.err {
  color: red;
  margin: 0;
}
</style>
