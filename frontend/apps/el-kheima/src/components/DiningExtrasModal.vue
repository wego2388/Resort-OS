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
import { useI18n } from 'vue-i18n'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
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

const { t, locale } = useI18n()
const { formatMoney } = useStaffFormat()

function localizedName(value: { name: string; name_ar: string | null }): string {
  return locale.value === 'ar' ? (value.name_ar || value.name) : value.name
}

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
    errorMsg.value = t('backoffice.pos.extrasModal.errors.selectVariant')
    return false
  }
  for (const group of groups.value) {
    if (group.group_type === 'text') {
      if (group.min_select >= 1 && !(textAnswers[group.id] ?? '').trim()) {
        errorMsg.value = t('backoffice.pos.extrasModal.errors.answerRequired', { group: localizedName(group) })
        return false
      }
      continue
    }
    const selectedCount = group.options.filter(o => selectedExtraIds.has(o.id)).length
    if (selectedCount < group.min_select) {
      errorMsg.value = t('backoffice.pos.extrasModal.errors.minimumRequired', {
        count: group.min_select,
        group: localizedName(group),
      })
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
  <AppModal :open="!!item" :title="item ? localizedName(item) : ''" size="md" :close-label="t('backoffice.pos.close')" @close="emit('close')">
    <div v-if="item" class="space-y-5">

      <!-- ── الحجم/النوع (Variant) ── -->
      <div v-if="availableVariants.length > 0">
        <h3 class="text-sm font-bold text-gray-800 dark:text-gray-200 mb-2">{{ t('backoffice.pos.extrasModal.variantTitle') }} <span class="text-danger">*</span></h3>
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
                : 'border-stone-200 dark:border-border hover:border-primary-300',
            ]"
          >
            <span class="font-semibold text-sm">{{ localizedName(variant) }}</span>
            <span class="font-bold text-primary-700 dark:text-primary-300">{{ formatMoney(variant.price, 'EGP') }}</span>
          </button>
        </div>
      </div>

      <!-- ── مجموعات الإضافات (pick_list + text) ── -->
      <div v-for="group in groups" :key="group.id">
        <h3 class="text-sm font-bold text-gray-800 dark:text-gray-200 mb-2 flex items-center gap-1.5">
          {{ localizedName(group) }}
          <AppBadge v-if="group.min_select >= 1" variant="warning" size="sm">{{ t('backoffice.pos.extrasModal.required') }}</AppBadge>
          <AppBadge v-else variant="neutral" size="sm">{{ t('backoffice.pos.extrasModal.optional') }}</AppBadge>
        </h3>

        <!-- free-text prompt group (e.g. "كام سمكة؟") -->
        <AppTextarea
          v-if="group.group_type === 'text'"
          v-model="textAnswers[group.id]"
          :rows="2"
          :placeholder="t('backoffice.pos.extrasModal.answerPlaceholder')"
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
                : 'border-stone-200 dark:border-border hover:border-primary-300',
              !opt.is_available ? 'opacity-40 cursor-not-allowed' : '',
            ]"
          >
            <span class="text-sm font-medium">{{ localizedName(opt) }}</span>
            <span v-if="Number(opt.price_addition) > 0" class="text-xs font-bold text-primary-700 dark:text-primary-300">+{{ formatMoney(opt.price_addition, 'EGP') }}</span>
          </button>
        </div>
      </div>

      <!-- ── ملاحظة حرة على الصنف ── -->
      <AppTextarea
        v-model="notes"
        :label="t('backoffice.pos.extrasModal.notesLabel')"
        :rows="2"
        :placeholder="t('backoffice.pos.extrasModal.notesPlaceholder')"
      />

      <p v-if="errorMsg" class="text-sm text-danger font-medium">{{ errorMsg }}</p>
    </div>

    <template #footer>
      <div class="flex items-center gap-2">
        <AppButton variant="ghost" @click="emit('close')">{{ t('backoffice.pos.extrasModal.cancel') }}</AppButton>
        <AppButton variant="primary" block @click="confirm">
          {{ t('backoffice.pos.extrasModal.addToCart', { amount: formatMoney(displayPrice, 'EGP') }) }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>
