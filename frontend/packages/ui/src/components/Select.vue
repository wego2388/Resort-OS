<script setup lang="ts">
// Deliberately a styled *native* <select>, not a custom listbox: keyboard
// nav, type-to-select, and mobile OS picker UI all come for free and fully
// accessible — a hand-built combobox buys nothing here and risks getting the
// a11y wrong. Combobox.vue (free-text + async filtering) is the separate
// component for when a native select's fixed option list isn't enough.
import { computed } from 'vue'
import AppIcon from './Icon.vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

export interface SelectOption {
  value: string | number
  label: string
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  placeholder?: string
  disabled?: boolean
  required?: boolean
  options: SelectOption[]
  modelValue?: string | number
}>(), { placeholder: 'اختر...' })

defineEmits<{ 'update:modelValue': [v: string] }>()

const classes = computed(() => [...fieldClasses({ error: !!props.error, disabled: props.disabled }), 'appearance-none pe-9 cursor-pointer'])
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :class="fieldLabelClasses">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </label>
    <div class="relative">
      <select
        :disabled="disabled"
        :required="required"
        :aria-invalid="!!error"
        :value="modelValue"
        @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
        :class="classes"
      >
        <option v-if="placeholder" value="" disabled :selected="modelValue === undefined || modelValue === ''">{{ placeholder }}</option>
        <option v-for="opt in options" :key="opt.value" :value="opt.value" :disabled="opt.disabled">{{ opt.label }}</option>
      </select>
      <AppIcon name="chevron-down" size="sm" class="absolute end-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted" />
    </div>
    <p v-if="error" :class="fieldErrorClasses">{{ error }}</p>
  </div>
</template>
