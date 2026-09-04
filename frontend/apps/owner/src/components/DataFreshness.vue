<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatApiTime, parseApiDateTime } from '../composables/useFormat'

const props = defineProps<{
  at: string
  refresh?: () => Promise<unknown> | unknown
}>()

const refreshing = ref(false)

const isStale = computed(() => {
  const timestamp = parseApiDateTime(props.at).getTime()
  return Number.isFinite(timestamp) && Date.now() - timestamp > 10 * 60_000
})

async function handleRefresh() {
  if (!props.refresh || refreshing.value) return
  refreshing.value = true
  try {
    await props.refresh()
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <div class="data-freshness" :class="isStale ? 'text-owner-amber' : 'text-owner-muted'">
    <span>
      <span class="inline-block h-1.5 w-1.5 rounded-full align-middle" :class="isStale ? 'bg-owner-amber' : 'bg-owner-green'" />
      آخر تحديث {{ formatApiTime(at) }}
    </span>
    <button
      v-if="refresh"
      type="button"
      class="min-h-11 rounded-lg px-3 font-semibold text-owner-text active:bg-owner-card disabled:opacity-50"
      :disabled="refreshing"
      :aria-label="refreshing ? 'جارٍ تحديث البيانات' : 'تحديث البيانات الآن'"
      @click="handleRefresh"
    >
      {{ refreshing ? 'جارٍ التحديث…' : 'تحديث الآن' }}
    </button>
  </div>
</template>
