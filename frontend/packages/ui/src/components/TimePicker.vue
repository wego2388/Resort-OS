<script setup lang="ts">
// Sibling of DatePicker.vue — same rationale (native <input type="time">
// over a custom widget). Value is always "HH:MM" 24h, the native shape.
import { computed } from 'vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

const props = defineProps<{
  label?: string
  error?: string
  disabled?: boolean
  required?: boolean
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
      type="time"
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
