<script setup lang="ts">
// stub — سيُكمَل في مرحلة لاحقة إذا طلب محمد
// الـ owner app تستخدم نفس 2FA setup flow من @resort-os/ui
import { useAuthStore } from '@resort-os/core'
const auth = useAuthStore()
</script>

<template>
  <div class="min-h-screen bg-owner-bg flex flex-col items-center justify-center px-6 text-center">
    <div class="text-4xl mb-4">🔐</div>
    <h2 class="text-owner-text font-bold mb-2">التحقق بخطوتين مطلوب</h2>
    <p class="text-owner-muted text-sm mb-6">
      حساب المالك يتطلب تفعيل التحقق بخطوتين لحماية البيانات المالية.
    </p>
    <p class="text-xs text-owner-amber">
      تواصل مع المدير لإعداد التحقق بخطوتين على حسابك.
    </p>
  </div>
</template>
