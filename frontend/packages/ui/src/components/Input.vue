<script setup lang="ts">
defineProps<{
  label?: string
  error?: string
  placeholder?: string
  type?: string
  disabled?: boolean
  modelValue?: string | number
}>()
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>
<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" class="text-sm font-medium text-gray-700">{{ label }}</label>
    <input
      :type="type ?? 'text'"
      :placeholder="placeholder"
      :disabled="disabled"
      :value="modelValue"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      :class="[
        'w-full px-3 py-2 rounded-lg border text-gray-900 placeholder-gray-400 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        error ? 'border-red-400 bg-red-50' : 'border-stone-200 bg-white',
        disabled ? 'opacity-50 cursor-not-allowed bg-gray-50' : '',
      ]"
    />
    <p v-if="error" class="text-xs text-red-600">{{ error }}</p>
  </div>
</template>
