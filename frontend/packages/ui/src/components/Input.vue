<script setup lang="ts">
// Visual output is byte-identical to before this refactor (see
// utils/inputClasses.ts for why) — this change only removes the duplicated
// Tailwind string that six new sibling components (Textarea, Select,
// MoneyInput, PhoneInput, DatePicker, TimePicker) would otherwise each have
// hand-copied. `required` is new and purely additive (renders nothing extra
// unless a label is also given).
import { computed, ref, useId } from 'vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses } from '../utils/inputClasses'

const props = defineProps<{
  label?: string
  error?: string
  placeholder?: string
  type?: string
  disabled?: boolean
  required?: boolean
  modelValue?: string | number
  /** Passed straight to the inner <input> — the component's root is a
   * wrapping <div>, so Vue's automatic attr fallthrough would otherwise
   * land these on the div instead of the actual input (silently doing
   * nothing). Explicit props are the only way to reach the real element. */
  autocomplete?: string
  inputmode?: 'none' | 'text' | 'decimal' | 'numeric' | 'tel' | 'search' | 'email' | 'url'
  autofocus?: boolean
  id?: string
}>()
defineEmits<{ 'update:modelValue': [v: string] }>()

const classes = computed(() => fieldClasses({ error: !!props.error, disabled: props.disabled }))
const generatedId = `app-input-${useId()}`
const inputId = computed(() => props.id ?? generatedId)
const errorId = computed(() => `${inputId.value}-error`)

// بيسمح لأي parent (زي StepUpConfirmModal) يعمل focus() فعلي على الـ<input>
// الحقيقي — الـroot هنا <div>، فـtemplate ref عادي على AppInput نفسه
// كان هيرجّع مكوّن Vue مش عنصر DOM يقدر يستقبل .focus().
const inputEl = ref<HTMLInputElement | null>(null)
defineExpose({ focus: () => inputEl.value?.focus() })
</script>
<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :for="inputId" :class="fieldLabelClasses">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </label>
    <input
      ref="inputEl"
      :id="inputId"
      :type="type ?? 'text'"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :aria-invalid="!!error"
      :aria-describedby="error ? errorId : undefined"
      :autocomplete="autocomplete"
      :inputmode="inputmode"
      :autofocus="autofocus"
      :value="modelValue"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      :class="classes"
    />
    <p v-if="error" :id="errorId" role="alert" :class="fieldErrorClasses">{{ error }}</p>
  </div>
</template>
