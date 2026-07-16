<script setup lang="ts">
/**
 * CommandPalette — global search + quick actions (Ctrl+K / Cmd+K).
 * مرجع: Linear، Vercel Dashboard.
 *
 * الاستخدام في BackOfficeLayout:
 *   <CommandPalette :open="show" :items="commands" @close="show=false" />
 *
 * يدعم:
 *  - Fuzzy search على label + sublabel + category
 *  - Recent items (localStorage — آخر 5)
 *  - Keyboard: Arrow/Enter/Escape
 *  - Teleport to body + z-[200]
 */
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import AppIcon from './Icon.vue'
import type { IconName } from '../icons/registry'

export interface CommandItem {
  id: string
  label: string
  sublabel?: string
  icon?: IconName
  category?: string
  shortcut?: string[]
  action: () => void
}

const RECENT_KEY = 'resort-os-command-recent'
const MAX_RECENT = 5

const props = withDefaults(defineProps<{
  open: boolean
  items: CommandItem[]
  loading?: boolean
  placeholder?: string
}>(), { placeholder: 'ابحث في النظام...' })

const emit = defineEmits<{ close: [] }>()

const inputRef    = ref<HTMLInputElement>()
const query       = ref('')
const activeIndex = ref(0)
const recentIds   = ref<string[]>([])

// تحميل الـ recent من localStorage
function loadRecent() {
  try { recentIds.value = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]') }
  catch { recentIds.value = [] }
}

function saveRecent(id: string) {
  const arr = [id, ...recentIds.value.filter(r => r !== id)].slice(0, MAX_RECENT)
  recentIds.value = arr
  localStorage.setItem(RECENT_KEY, JSON.stringify(arr))
}

// ── Fuzzy search ──────────────────────────────────────────────────────────
function fuzzyScore(item: CommandItem, q: string): number {
  const text = `${item.label} ${item.sublabel ?? ''} ${item.category ?? ''}`.toLowerCase()
  const query = q.toLowerCase()
  if (text.includes(query)) return query.length / text.length
  // حرف حرف matching
  let score = 0
  let ti = 0
  for (const ch of query) {
    const found = text.indexOf(ch, ti)
    if (found === -1) return 0
    score += 1 / (found - ti + 1)
    ti = found + 1
  }
  return score
}

const filteredItems = computed(() => {
  if (!query.value.trim()) {
    // بدون query → عرض الـ recent أولاً ثم الباقي
    const recentItems = recentIds.value
      .map(id => props.items.find(i => i.id === id))
      .filter(Boolean) as CommandItem[]
    const rest = props.items.filter(i => !recentIds.value.includes(i.id)).slice(0, 8)
    return [...recentItems, ...rest]
  }

  return props.items
    .map(item => ({ item, score: fuzzyScore(item, query.value) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .map(({ item }) => item)
    .slice(0, 10)
})

// تجميع حسب category لعرض أنيق
const grouped = computed(() => {
  const map = new Map<string, CommandItem[]>()
  for (const item of filteredItems.value) {
    const g = !query.value && recentIds.value.includes(item.id) ? 'الأخيرة' : (item.category ?? 'إجراءات')
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(item)
  }
  return map
})

// ── Execute ───────────────────────────────────────────────────────────────
function execute(item: CommandItem) {
  saveRecent(item.id)
  item.action()
  emit('close')
  query.value = ''
}

// ── Keyboard ──────────────────────────────────────────────────────────────
function handleKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      activeIndex.value = Math.min(activeIndex.value + 1, filteredItems.value.length - 1)
      break
    case 'ArrowUp':
      e.preventDefault()
      activeIndex.value = Math.max(activeIndex.value - 1, 0)
      break
    case 'Enter':
      e.preventDefault()
      if (filteredItems.value[activeIndex.value]) execute(filteredItems.value[activeIndex.value])
      break
    case 'Escape':
      emit('close')
      query.value = ''
      break
  }
}

// Reset state عند الفتح
watch(() => props.open, (v) => {
  if (v) {
    query.value = ''
    activeIndex.value = 0
    loadRecent()
    nextTick(() => inputRef.value?.focus())
  }
})

// Reset active عند تغيير الـ results
watch(filteredItems, () => { activeIndex.value = 0 })

// Ctrl+K / Cmd+K من أي مكان
function handleGlobalKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    if (props.open) emit('close')
    // لو مغلق: المستخدم في BackOfficeLayout يفتحه بنفسه
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleGlobalKey)
  loadRecent()
})
onBeforeUnmount(() => document.removeEventListener('keydown', handleGlobalKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="cp">
      <div v-if="open" class="fixed inset-0 z-[200] flex items-start justify-center pt-[15vh] px-4" dir="rtl">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="emit('close')" />

        <!-- Panel -->
        <div class="relative w-full max-w-xl bg-white dark:bg-surface rounded-2xl shadow-elevation-5 overflow-hidden animate-ds-scale-in">
          <!-- Search input -->
          <div class="flex items-center gap-3 px-4 py-3.5 border-b border-stone-100 dark:border-border">
            <svg v-if="loading" class="animate-spin h-5 w-5 text-muted shrink-0" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            <AppIcon v-else name="search" size="md" class="text-muted shrink-0" />
            <input
              ref="inputRef"
              v-model="query"
              type="text"
              :placeholder="placeholder"
              class="flex-1 bg-transparent text-base text-gray-900 dark:text-gray-100 placeholder-muted outline-none"
              @keydown="handleKeydown"
            />
            <kbd class="hidden sm:flex items-center gap-1 px-2 py-1 text-[10px] font-semibold text-muted bg-stone-100 dark:bg-gray-700 rounded-md border border-stone-200 dark:border-border">
              ESC
            </kbd>
          </div>

          <!-- Results -->
          <div class="max-h-[60vh] overflow-y-auto">
            <div v-if="!filteredItems.length" class="flex flex-col items-center gap-2 py-10 text-muted">
              <AppIcon name="search" size="xl" class="opacity-30" />
              <span class="text-sm">{{ query ? `لا نتائج لـ "${query}"` : 'ابدأ الكتابة للبحث' }}</span>
            </div>

            <template v-for="[group, groupItems] in grouped" :key="group">
              <!-- Group header -->
              <div class="px-4 py-2 text-[10px] font-bold text-muted uppercase tracking-wider bg-stone-50/80 dark:bg-gray-800/80 sticky top-0">
                {{ group }}
              </div>
              <!-- Items -->
              <button
                v-for="item in groupItems"
                :key="item.id"
                type="button"
                :class="[
                  'w-full flex items-center gap-3 px-4 py-3 text-start transition-colors',
                  filteredItems.indexOf(item) === activeIndex
                    ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                    : 'text-gray-800 dark:text-gray-200 hover:bg-stone-50 dark:hover:bg-gray-700/50',
                ]"
                @click="execute(item)"
                @mouseenter="activeIndex = filteredItems.indexOf(item)"
              >
                <!-- Icon -->
                <div :class="[
                  'w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm',
                  filteredItems.indexOf(item) === activeIndex
                    ? 'bg-primary-100 dark:bg-primary-800/50 text-primary-700 dark:text-primary-400'
                    : 'bg-stone-100 dark:bg-gray-700 text-muted',
                ]">
                  <AppIcon v-if="item.icon" :name="item.icon" size="sm" />
                  <span v-else class="text-xs font-bold">{{ item.label.charAt(0) }}</span>
                </div>

                <!-- Labels -->
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-semibold truncate">{{ item.label }}</div>
                  <div v-if="item.sublabel" class="text-xs text-muted truncate">{{ item.sublabel }}</div>
                </div>

                <!-- Shortcut -->
                <div v-if="item.shortcut?.length" class="hidden sm:flex items-center gap-1 shrink-0">
                  <kbd v-for="key in item.shortcut" :key="key"
                    class="px-1.5 py-0.5 text-[10px] font-semibold text-muted bg-stone-100 dark:bg-gray-700 rounded border border-stone-200 dark:border-border">
                    {{ key }}
                  </kbd>
                </div>
              </button>
            </template>
          </div>

          <!-- Footer hint -->
          <div class="flex items-center gap-4 px-4 py-2.5 border-t border-stone-100 dark:border-border text-[11px] text-muted bg-stone-50/50 dark:bg-gray-800/50">
            <span class="flex items-center gap-1"><kbd class="px-1 py-0.5 bg-stone-200 dark:bg-gray-700 rounded text-[10px]">↑↓</kbd> تنقل</span>
            <span class="flex items-center gap-1"><kbd class="px-1 py-0.5 bg-stone-200 dark:bg-gray-700 rounded text-[10px]">↵</kbd> تنفيذ</span>
            <span class="flex items-center gap-1"><kbd class="px-1 py-0.5 bg-stone-200 dark:bg-gray-700 rounded text-[10px]">ESC</kbd> إغلاق</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cp-enter-active, .cp-leave-active { transition: opacity 150ms ease; }
.cp-enter-from, .cp-leave-to { opacity: 0; }
</style>
