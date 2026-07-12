<script setup lang="ts">
import { computed } from 'vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  placeholder?: string
  disabled?: boolean
  required?: boolean
  rows?: number
  modelValue?: string
}>(), { rows: 3 })

defineEmits<{ 'update:modelValue': [v: string] }>()

const classes = computed(() => [...fieldClasses({ error: !!props.error, disabled: props.disabled }), 'resize-y min-h-[5rem]'])
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :class="fieldLabelClasses">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </label>
    <textarea
      :rows="rows"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :aria-invalid="!!error"
      :value="modelValue"
      @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      :class="classes"
    />
    <p v-if="error" :class="fieldErrorClasses">{{ error }}</p>
  </div>
</template>
