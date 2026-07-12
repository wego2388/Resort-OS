<script setup lang="ts">
// A currency amount field — input masking is presentation logic (allowed in
// components per CLAUDE.md §4), the actual financial rules (rounding,
// Decimal precision, VAT, ...) all stay backend-side exactly as today; this
// component only ever emits a plain numeric *string* (never a JS `number`)
// so a caller sending it straight to the API never loses precision to
// float rounding before the request even leaves the browser.
import { computed } from 'vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  disabled?: boolean
  required?: boolean
  /** Defaults to EGP — the only currency this system's `DEFAULT_CURRENCY` env var is ever actually set to in production. */
  currency?: string
  modelValue?: string
}>(), { currency: 'ج.م' })

const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

function onInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value
  // Allow digits + a single decimal point, max 2 fraction digits — mirrors
  // the backend's Numeric(12, 2) columns (CLAUDE.md §16), it doesn't invent
  // a new precision rule.
  const cleaned = raw.replace(/[^\d.]/g, '')
  const parts = cleaned.split('.')
  const normalized = parts.length > 1 ? `${parts[0]}.${parts.slice(1).join('').slice(0, 2)}` : cleaned
  emit('update:modelValue', normalized)
}

const classes = computed(() => [...fieldClasses({ error: !!props.error, disabled: props.disabled, withEndSlot: true }), 'text-end tabular-nums'])
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :class="fieldLabelClasses">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </label>
    <div class="relative">
      <input
        type="text"
        inputmode="decimal"
        placeholder="0.00"
        :disabled="disabled"
        :required="required"
        :aria-invalid="!!error"
        :value="modelValue"
        @input="onInput"
        :class="classes"
      />
      <span class="absolute end-3 top-1/2 -translate-y-1/2 text-sm text-muted pointer-events-none">{{ currency }}</span>
    </div>
    <p v-if="error" :class="fieldErrorClasses">{{ error }}</p>
  </div>
</template>
