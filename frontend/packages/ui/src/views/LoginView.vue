<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@resort-os/core'
import { useToast } from '../composables/useToast'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const toast = useToast()
const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) return
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch {
    toast.error('اسم المستخدم أو كلمة المرور غير صحيحة')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="w-20 h-20 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-4 backdrop-blur">
          <svg class="w-10 h-10 text-amber-300" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
        </div>
        <h1 class="text-3xl font-bold text-white mb-1">Resort OS</h1>
        <p class="text-blue-200 text-sm">نظام إدارة المنتجع المتكامل</p>
      </div>

      <!-- Form -->
      <div class="bg-white rounded-2xl p-8 shadow-2xl">
        <h2 class="text-xl font-bold text-gray-900 mb-6 text-center">تسجيل الدخول</h2>
        <form @submit.prevent="handleLogin" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">اسم المستخدم</label>
            <input
              v-model="username"
              type="text"
              placeholder="username"
              autocomplete="username"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">كلمة المرور</label>
            <input
              v-model="password"
              type="password"
              placeholder="••••••••"
              autocomplete="current-password"
              class="w-full px-4 py-3 rounded-xl border border-stone-200 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900"
            />
          </div>
          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-blue-700 text-white py-3 rounded-xl font-semibold hover:bg-blue-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <svg v-if="loading" class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            {{ loading ? 'جاري الدخول...' : 'دخول' }}
          </button>
        </form>
        <p class="text-center text-xs text-gray-400 mt-6">Blue Bay El Kheima — Resort OS v1.0</p>
      </div>
    </div>
  </div>
</template>
