<script setup lang="ts">
// 2026-09-11: registerType بقى 'prompt' (راجع vite.config.ts) — نسخة جديدة
// من التطبيق بتتنزّل في الخلفية لكن ماتاخدش السيطرة إلا لما الموظف يضغط
// هنا صراحةً، عشان تحديث ماياخدش سلة طلب لسه ماتبعتتش أو اتدفعتش على تابلت
// شغّال طول اليوم.
import { useI18n } from 'vue-i18n'
import { useRegisterSW } from 'virtual:pwa-register/vue'
import { AppIcon } from '@resort-os/ui'

const { t } = useI18n()
const { needRefresh, updateServiceWorker } = useRegisterSW()

function reload() {
  updateServiceWorker(true)
}
</script>

<template>
  <div
    v-if="needRefresh"
    role="status"
    aria-live="polite"
    class="fixed inset-x-0 bottom-0 z-50 flex items-center justify-between gap-3 border-t border-primary-800 bg-primary-950 px-4 py-3 text-white shadow-lg"
  >
    <div class="flex items-center gap-2 font-bold">
      <AppIcon name="refresh" size="sm" />
      <span>{{ t('backoffice.layout.updateAvailable') }}</span>
    </div>
    <button
      type="button"
      class="min-h-11 rounded-xl bg-white px-4 text-sm font-black text-primary-900 active:scale-[0.98]"
      @click="reload"
    >
      {{ t('backoffice.layout.updateNow') }}
    </button>
  </div>
</template>
