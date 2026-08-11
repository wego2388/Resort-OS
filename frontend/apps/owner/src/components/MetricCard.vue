<script setup lang="ts">
/**
 * MetricCard — بطاقة المقياس الأساسية.
 * رقم واحد كبير + label + sparkline + delta + provisional badge.
 * قرار 0004: لا يُقدَّم رقم provisional كأنه نهائي.
 */
import SparkLine from './SparkLine.vue'
import { deltaClass, deltaArrow } from '../composables/useFormat'

const props = defineProps<{
  label: string
  value: string          // مُنسَّق مسبقاً
  delta?: string | null  // مثال: "+11% عن أمس"
  deltaValue?: string | number | null
  sparkValues?: number[]
  isProvisional?: boolean
  loading?: boolean
  /** لون الرقم: green/red/amber/default */
  colorScheme?: 'green' | 'red' | 'amber' | 'default'
  /** نص إضافي صغير تحت الرقم */
  subtitle?: string
  /** لو موجود، بيظهر زرار تثبيت (المفضلة — Phase 8) */
  pinned?: boolean
}>()

const emit = defineEmits<{ 'toggle-pin': [] }>()
</script>

<template>
  <div class="owner-card" role="region" :aria-label="label">
    <!-- Header: label + provisional + pin -->
    <div class="flex items-start justify-between mb-3">
      <span class="text-xs font-semibold text-owner-muted uppercase tracking-wider">
        {{ label }}
      </span>
      <div class="flex items-center gap-2">
        <span v-if="isProvisional" class="provisional-badge" role="status" aria-label="غير نهائي">
          ⏳ مؤقت
        </span>
        <button
          v-if="pinned !== undefined"
          class="touch-target -m-2 p-2 text-lg leading-none transition-colors"
          :class="pinned ? 'text-owner-amber' : 'text-owner-border active:text-owner-muted'"
          :aria-label="pinned ? 'إلغاء التثبيت' : 'تثبيت في المفضلة'"
          @click="emit('toggle-pin')"
        >{{ pinned ? '★' : '☆' }}</button>
      </div>
    </div>

    <!-- Skeleton لو loading -->
    <template v-if="loading">
      <div class="skeleton h-9 w-3/4 mb-3 rounded" />
      <div class="skeleton h-10 w-full mb-2 rounded" />
      <div class="skeleton h-4 w-1/3 rounded" />
    </template>

    <template v-else>
      <!-- الرقم الكبير -->
      <div
        class="metric-value mb-1"
        :class="{
          'text-owner-green': colorScheme === 'green',
          'text-owner-red':   colorScheme === 'red',
          'text-owner-amber': colorScheme === 'amber',
          'text-owner-text':  !colorScheme || colorScheme === 'default',
        }"
      >
        {{ value }}
      </div>

      <!-- subtitle -->
      <div v-if="subtitle" class="text-xs text-owner-muted mb-2">{{ subtitle }}</div>

      <!-- Sparkline -->
      <SparkLine
        v-if="sparkValues && sparkValues.length > 1"
        :values="sparkValues"
        class="mb-2"
      />

      <!-- Delta -->
      <div
        v-if="delta || deltaValue !== undefined"
        class="text-xs font-semibold flex items-center gap-1"
        :class="deltaClass(deltaValue)"
        aria-live="polite"
      >
        <span>{{ deltaArrow(deltaValue) }}</span>
        <span>{{ delta }}</span>
      </div>
    </template>
  </div>
</template>
