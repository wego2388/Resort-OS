<script setup lang="ts">
// A styled native <input type="date"> — deliberately not a hand-built
// calendar widget. The native picker gets locale-correct formatting, full
// keyboard support, and the OS/mobile-native date UI for free; re-inventing
// that as a custom component is a large, easy-to-get-wrong a11y surface for
// a need the platform already solves well. Value is always a plain
// YYYY-MM-DD string (native <input type="date"> shape) — matches what every
// backend endpoint in this project already expects for a `date` field.
import { computed } from 'vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

const props = defineProps<{
  label?: string
  error?: string
  disabled?: boolean
  required?: boolean
  min?: string
  max?: string
  modelValue?: string
}>()

defineEmits<{ 'update:modelValue': [v: string] }>()

const classes = computed(() => [...fieldClasses({ error: !!props.error, disabled: props.disabled }), 'tabular-nums'])
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :class="fieldLabelClasses">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </label>
    <input
      type="date"
      :min="min"
      :max="max"
      :disabled="disabled"
      :required="required"
      :aria-invalid="!!error"
      :value="modelValue"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      :class="classes"
    />
    <p v-if="error" :class="fieldErrorClasses">{{ error }}</p>
  </div>
</template>
