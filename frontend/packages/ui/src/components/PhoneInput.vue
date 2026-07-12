<script setup lang="ts">
// Egyptian mobile number entry — every phone number in this system (guest
// profiles, employees, B2B contacts) is a local Egyptian line, so the +20
// country code is a fixed prefix rather than a full international selector;
// that's a real, deliberate scope reduction, not a missing feature.
import { computed } from 'vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  disabled?: boolean
  required?: boolean
  /** Local digits only, no country code (e.g. "1012345678") — `update:modelValue` always emits this same shape. */
  modelValue?: string
}>(), {})

const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

function onInput(e: Event) {
  const digitsOnly = (e.target as HTMLInputElement).value.replace(/\D/g, '').slice(0, 10)
  emit('update:modelValue', digitsOnly)
}

// A valid Egyptian mobile local number is 10 digits starting with 1 (01X…
// without the leading 0, which the +20 prefix already replaces).
const isValidLength = computed(() => !props.modelValue || /^1\d{9}$/.test(props.modelValue))
const classes = computed(() => [...fieldClasses({ error: !!props.error || !isValidLength.value, disabled: props.disabled, withStartSlot: true }), 'tabular-nums'])
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :class="fieldLabelClasses">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </label>
    <div class="relative" dir="ltr">
      <span class="absolute start-3 top-1/2 -translate-y-1/2 text-sm text-muted pointer-events-none">+20</span>
      <input
        type="tel"
        inputmode="numeric"
        placeholder="1012345678"
        :disabled="disabled"
        :required="required"
        :aria-invalid="!!error || !isValidLength"
        :value="modelValue"
        @input="onInput"
        :class="classes"
      />
    </div>
    <p v-if="error" :class="fieldErrorClasses">{{ error }}</p>
    <p v-else-if="modelValue && !isValidLength" :class="fieldErrorClasses">رقم الموبايل يجب أن يبدأ بـ 1 ويتكون من 10 أرقام</p>
  </div>
</template>
