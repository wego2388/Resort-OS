<script setup lang="ts">
// Booking confirmation page
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<template>
  <div class="min-h-screen bg-resort-bg flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl p-8 text-center shadow-sm border border-resort-border max-w-sm w-full">
      <div class="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
        </svg>
      </div>
      <h2 class="font-heading text-xl font-bold text-brand-charcoal mb-2">{{ t('marketing.confirmation.title') }}</h2>
      <p class="text-gray-500 text-sm font-body">{{ t('marketing.confirmation.body') }}</p>
      <RouterLink to="/" class="mt-4 inline-block text-brand-ocean font-medium text-sm">{{ t('marketing.confirmation.backHome') }}</RouterLink>
    </div>
  </div>
</template>
