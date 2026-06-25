<template>
  <div v-if="isAuthenticated" class="user-menu">
    <span class="user-email">{{ user?.name || user?.email }}</span>
    <router-link v-if="isAdmin" to="/admin/users" class="admin-link">
      {{ $t('auth.admin.usersTitle') }}
    </router-link>
    <button class="logout-btn" @click="handleLogout">
      {{ $t('auth.logout') }}
    </button>
  </div>
</template>

<script setup>
import { useAuth } from '@/stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuth()
const router = useRouter()

const { user, isAuthenticated, isAdmin } = auth

async function handleLogout() {
  await auth.logout()
  router.replace('/login')
}
</script>

<style scoped>
.user-menu {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}

.user-email {
  color: #555;
  white-space: nowrap;
}

.admin-link {
  color: #FF4500;
  text-decoration: none;
  border: 1px solid #FF4500;
  padding: 4px 10px;
  transition: background 0.2s, color 0.2s;
}

.admin-link:hover {
  background: #FF4500;
  color: #fff;
}

.logout-btn {
  background: transparent;
  color: #333;
  border: 1px solid #CCC;
  padding: 4px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  cursor: pointer;
  transition: border-color 0.2s, opacity 0.2s;
}

.logout-btn:hover {
  border-color: #999;
}
</style>
