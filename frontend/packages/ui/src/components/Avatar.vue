<script setup lang="ts">
// User/guest avatar — photo when available, otherwise initials on a
// deterministic color (same name always gets the same color, so a list of
// avatars stays visually distinguishable without a photo for everyone).
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  name: string
  src?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}>(), { size: 'md' })

const initials = computed(() => {
  const parts = props.name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  return parts.length === 1 ? parts[0]!.slice(0, 2) : `${parts[0]![0]}${parts[1]![0]}`
})

// A small fixed palette (not the DS primary/secondary tokens — those carry
// specific brand/semantic meaning elsewhere) hashed from the name so it's
// stable across renders/sessions for the same person.
const PALETTE = [
  'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300',
  'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300',
  'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300',
  'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
  'bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300',
  'bg-cyan-100 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300',
]
const colorClass = computed(() => {
  let hash = 0
  for (const ch of props.name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return PALETTE[hash % PALETTE.length]
})

const sizeClass = computed(() => ({
  xs: 'w-6 h-6 text-xs',
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-sm',
  lg: 'w-12 h-12 text-base',
  xl: 'w-16 h-16 text-lg',
}[props.size]))
</script>

<template>
  <img
    v-if="src"
    :src="src"
    :alt="name"
    :class="[sizeClass, 'rounded-full object-cover shrink-0']"
  />
  <div
    v-else
    :class="[sizeClass, colorClass, 'rounded-full flex items-center justify-center font-semibold shrink-0 select-none']"
    :title="name"
  >
    {{ initials }}
  </div>
</template>
