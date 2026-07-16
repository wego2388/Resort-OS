<script setup lang="ts">
/**
 * DiningExtrasModal — variant (size/type) + extra-group picker for a single
 * dining item, opened from UnifiedPOSView before the item is added to the
 * cart. Mirrors RestaurantPOSView's inline variantPicker, generalized to
 * also resolve extra_groups (pick_list *and* the new free-text group_type,
 * see app/modules/dining/models.py::DiningItemExtraGroup — a real gap vs.
 * the resort's previous POS, "كام سمكة؟" as a structured text prompt, not
 * just a multi-select modifier list).
 *
 * Pure presentation — all validation the server also enforces (min/max
 * select, required text) is mirrored here only so the cashier gets instant
 * feedback; app/modules/dining/services.py::_resolve_extras remains the
 * real source of truth (CLAUDE.md §4: no business logic trusted client-side).
 */
import { computed, reactive, ref, watch } from 'vue'
import { AppModal, AppButton, AppBadge, AppTextarea } from '@resort-os/ui'

interface DiningExtra {
  id: number; name: string; name_ar: string | null
  price_addition: number | string; is_available: boolean
}
interface DiningExtraGroup {
  id: number; name: string; name_ar: string | null
  group_type: 'pick_list' | 'text'
  min_select: number; max_select: number
  options: DiningExtra[]
}
interface DiningVariant {
  id: number; name: string; name_ar: string | null
  price: number | string; is_available: boolean
}
export interface DiningExtrasItem {
  id: number; name: string; name_ar: string | null
  price: number | string
  image_url?: string | null
  variants?: DiningVariant[]
  extra_groups?: DiningExtraGroup[]
}

const props = defineProps<{ item: DiningExtrasItem | null }>()
const emit = defineEmits<{
  confirm: [{ variantId: number | null; extraIds: number[]; extraTexts: Record<number, string>; notes: string }]
  close: []
}>()

const availableVariants = computed(() => (props.item?.variants ?? []).filter(v => v.is_available))
const groups = computed(() => props.item?.extra_groups ?? [])

const selectedVariantId = ref<number | null>(null)
const selectedExtraIds = reactive<Set<number>>(new Set())
const textAnswers = reactive<Record<number, string>>({})
const notes = ref('')
const errorMsg = ref('')

watch(() => props.item, (item) => {
  selectedVariantId.value = availableVariants.value.length === 1 ? availableVariants.value[0]!.id : null
  selectedExtraIds.clear()
  for (const key of Object.keys(textAnswers)) delete textAnswers[Number(key)]
  notes.value = ''
  errorMsg.value = ''
  if (!item) return
}, { immediate: true })

function toggleExtra(group: DiningExtraGroup, optionId: number) {
  const singleSelect = group.max_select === 1
  if (singleSelect) {
    // Clear any other selection in this group first (radio behavior).
    for (const opt of group.options) if (opt.id !== optionId) selectedExtraIds.delete(opt.id)
    selectedExtraIds.has(optionId) ? selectedExtraIds.delete(optionId) : selectedExtraIds.add(optionId)
    return
  }
  if (selectedExtraIds.has(optionId)) {
    selectedExtraIds.delete(optionId)
    return
  }
  const currentInGroup = group.options.filter(o => selectedExtraIds.has(o.id)).length
  if (currentInGroup >= group.max_select) return
  selectedExtraIds.add(optionId)
}

const displayPrice = computed(() => {
  if (!props.item) return 0
  const variant = availableVariants.value.find(v => v.id === selectedVariantId.value)
  const base = Number(variant ? variant.price : props.item.price)
  const extrasTotal = groups.value
    .filter(g => g.group_type === 'pick_list')
    .flatMap(g => g.options)
    .filter(o => selectedExtraIds.has(o.id))
    .reduce((s, o) => s + Number(o.price_addition), 0)
  return base + extrasTotal
})

function validate(): boolean {
  if (availableVariants.value.length > 0 && selectedVariantId.value === null) {
    errorMsg.value = 'لازم تختار الحجم/النوع'
    return false
  }
  for (const group of groups.value) {
    if (group.group_type === 'text') {
      if (group.min_select >= 1 && !(textAnswers[group.id] ?? '').trim()) {
        errorMsg.value = `لازم تدخل قيمة لـ "${group.name_ar || group.name}"`
        return false
      }
      continue
    }
    const selectedCount = group.options.filter(o => selectedExtraIds.has(o.id)).length
    if (selectedCount < group.min_select) {
      errorMsg.value = `لازم تختار ${group.min_select} على الأقل من "${group.name_ar || group.name}"`
      return false
    }
  }
  errorMsg.value = ''
  return true
}

function confirm() {
  if (!validate()) return
  const extraTexts: Record<number, string> = {}
  for (const group of groups.value) {
    if (group.group_type === 'text' && (textAnswers[group.id] ?? '').trim()) {
      extraTexts[group.id] = textAnswers[group.id]!.trim()
    }
  }
  emit('confirm', {
    variantId: selectedVariantId.value,
    extraIds: [...selectedExtraIds],
    extraTexts,
    notes: notes.value.trim(),
  })
}
</script>

<template>
  <AppModal :open="!!item" :title="item ? (item.name_ar || item.name) : ''" size="md" @close="emit('close')">
    <div v-if="item" dir="rtl" class="space-y-5">

      <!-- ── الحجم/النوع (Variant) ── -->
      <div v-if="availableVariants.length > 0">
        <h3 class="text-sm font-bold text-gray-800 mb-2">الحجم/النوع <span class="text-danger">*</span></h3>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="variant in availableVariants"
            :key="variant.id"
            type="button"
            @click="selectedVariantId = variant.id"
            :class="[
              'flex items-center justify-between gap-2 p-3 rounded-xl border-2 text-start transition-all min-h-[48px]',
              selectedVariantId === variant.id
                ? 'border-primary-600 bg-primary-50 text-primary-800'
                : 'border-stone-200 hover:border-primary-300',
            ]"
          >
            <span class="font-semibold text-sm">{{ variant.name_ar || variant.name }}</span>
            <span class="font-bold text-primary-700">{{ variant.price }} ج</span>
          </button>
        </div>
      </div>

      <!-- ── مجموعات الإضافات (pick_list + text) ── -->
      <div v-for="group in groups" :key="group.id">
        <h3 class="text-sm font-bold text-gray-800 mb-2 flex items-center gap-1.5">
          {{ group.name_ar || group.name }}
          <AppBadge v-if="group.min_select >= 1" variant="warning" size="sm">إجباري</AppBadge>
          <AppBadge v-else variant="neutral" size="sm">اختياري</AppBadge>
        </h3>

        <!-- free-text prompt group (e.g. "كام سمكة؟") -->
        <AppTextarea
          v-if="group.group_type === 'text'"
          v-model="textAnswers[group.id]"
          :rows="2"
          :placeholder="`اكتب الإجابة هنا...`"
        />

        <!-- pick-list group -->
        <div v-else class="grid grid-cols-2 gap-2">
          <button
            v-for="opt in group.options"
            :key="opt.id"
            type="button"
            :disabled="!opt.is_available"
            @click="toggleExtra(group, opt.id)"
            :class="[
              'flex items-center justify-between gap-2 p-2.5 rounded-xl border-2 text-start transition-all min-h-[48px]',
              selectedExtraIds.has(opt.id)
                ? 'border-primary-600 bg-primary-50 text-primary-800'
                : 'border-stone-200 hover:border-primary-300',
              !opt.is_available ? 'opacity-40 cursor-not-allowed' : '',
            ]"
          >
            <span class="text-sm font-medium">{{ opt.name_ar || opt.name }}</span>
            <span v-if="Number(opt.price_addition) > 0" class="text-xs font-bold text-primary-700">+{{ opt.price_addition }} ج</span>
          </button>
        </div>
      </div>

      <!-- ── ملاحظة حرة على الصنف ── -->
      <AppTextarea v-model="notes" label="ملاحظة (اختياري)" :rows="2" placeholder="مثال: بدون ثوم، حار جدًا" />

      <p v-if="errorMsg" class="text-sm text-danger font-medium">{{ errorMsg }}</p>
    </div>

    <template #footer>
      <div class="flex items-center gap-2">
        <AppButton variant="ghost" @click="emit('close')">إلغاء</AppButton>
        <AppButton variant="primary" block @click="confirm">
          إضافة للسلة — {{ displayPrice.toFixed(2) }} ج
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>
