<script setup lang="ts">
// ExtrasSelectionModal — shown when a waiter taps a menu item that has
// extra_groups (MenuItemExtraGroupRead[]) before it's allowed into the cart.
// max_select === 1 → radio group (single choice), otherwise → checkboxes
// capped at max_select. min_select is enforced client-side so a waiter can't
// even attempt to add a doomed line (the backend re-validates the same rule
// in services._resolve_extras, so this is a UX guard, not the source of truth).
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppModal, AppButton } from '@resort-os/ui'

interface ExtraOption {
  id: number
  name: string
  name_ar?: string | null
  price_addition: number | string
  is_available: boolean
}
interface ExtraGroup {
  id: number
  name: string
  name_ar?: string | null
  min_select: number
  max_select: number
  options: ExtraOption[]
}
interface MenuItemLike {
  id: number
  name: string
  name_ar?: string | null
  price: number | string
  extra_groups: ExtraGroup[]
}

const props = defineProps<{ item: MenuItemLike | null }>()
const emit = defineEmits<{
  confirm: [extraIds: number[], extras: ExtraOption[]]
  close: []
}>()
const { t, locale } = useI18n()
const { formatMoney } = useStaffFormat()

function localizedName(value: { name: string; name_ar?: string | null }): string {
  return locale.value === 'ar' ? (value.name_ar || value.name) : value.name
}

// group id -> selected option ids
const selection = ref<Record<number, number[]>>({})

watch(
  () => props.item,
  (item) => {
    selection.value = {}
    if (item) {
      for (const group of item.extra_groups) selection.value[group.id] = []
    }
  },
  { immediate: true },
)

function toggleSingle(group: ExtraGroup, optionId: number) {
  selection.value[group.id] = [optionId]
}

function toggleMulti(group: ExtraGroup, optionId: number) {
  const current = selection.value[group.id] ?? []
  if (current.includes(optionId)) {
    selection.value[group.id] = current.filter((id) => id !== optionId)
  } else {
    if (current.length >= group.max_select) return // capped — swap out oldest pick
    selection.value[group.id] = [...current, optionId]
  }
}

function isSelected(groupId: number, optionId: number): boolean {
  return (selection.value[groupId] ?? []).includes(optionId)
}

const groupErrors = computed(() => {
  if (!props.item) return [] as string[]
  const errors: string[] = []
  for (const group of props.item.extra_groups) {
    const count = (selection.value[group.id] ?? []).length
    if (count < group.min_select) {
      errors.push(t('backoffice.extrasSelection.requiredMin', {
        count: group.min_select,
        name: localizedName(group),
      }))
    }
  }
  return errors
})

const canConfirm = computed(() => groupErrors.value.length === 0)

const selectedExtras = computed<ExtraOption[]>(() => {
  if (!props.item) return []
  const all: ExtraOption[] = []
  for (const group of props.item.extra_groups) {
    for (const optId of selection.value[group.id] ?? []) {
      const opt = group.options.find((o) => o.id === optId)
      if (opt) all.push(opt)
    }
  }
  return all
})

const extrasTotal = computed(() =>
  selectedExtras.value.reduce((s, e) => s + Number(e.price_addition), 0),
)

function confirm() {
  if (!canConfirm.value) return
  emit(
    'confirm',
    selectedExtras.value.map((e) => e.id),
    selectedExtras.value,
  )
}
</script>

<template>
  <AppModal :open="!!item" :title="item ? localizedName(item) : ''" size="sm" @close="emit('close')">
    <div v-if="item" class="space-y-5">
      <div v-for="group in item.extra_groups" :key="group.id" class="space-y-2">
        <div class="flex items-center justify-between">
          <h4 class="text-sm font-bold text-gray-800 dark:text-gray-200">{{ localizedName(group) }}</h4>
          <span class="text-xs text-gray-500 dark:text-gray-400">
            {{ group.max_select === 1 ? t('backoffice.extrasSelection.chooseOne') : t('backoffice.extrasSelection.upTo', { count: group.max_select }) }}
            <span v-if="group.min_select > 0" class="text-amber-600 dark:text-amber-300"> — {{ t('backoffice.extrasSelection.required') }}</span>
          </span>
        </div>

        <div class="space-y-1.5">
          <button
            v-for="opt in group.options"
            :key="opt.id"
            type="button"
            :disabled="!opt.is_available"
            @click="group.max_select === 1 ? toggleSingle(group, opt.id) : toggleMulti(group, opt.id)"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl border-2 text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            :class="isSelected(group.id, opt.id)
              ? 'border-blue-600 bg-blue-50 text-blue-800 dark:bg-blue-950/30 dark:text-blue-200'
              : 'border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 hover:border-blue-200 dark:hover:border-blue-800'"
          >
            <span class="flex items-center gap-2">
              <span
                class="w-4 h-4 flex-shrink-0 flex items-center justify-center border-2"
                :class="[
                  group.max_select === 1 ? 'rounded-full' : 'rounded',
                  isSelected(group.id, opt.id) ? 'border-blue-600 bg-blue-600' : 'border-stone-300',
                ]"
              >
                <span v-if="isSelected(group.id, opt.id)" class="w-1.5 h-1.5 rounded-full bg-white dark:bg-surface" />
              </span>
              {{ localizedName(opt) }}
            </span>
            <span v-if="Number(opt.price_addition) > 0" class="text-xs font-bold text-blue-700 dark:text-blue-300">
              +{{ formatMoney(opt.price_addition, 'EGP') }}
            </span>
          </button>
        </div>
      </div>

      <div v-if="groupErrors.length" role="alert" class="space-y-1 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
        <p v-for="(err, i) in groupErrors" :key="i">⚠️ {{ err }}</p>
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-bold text-gray-900 dark:text-gray-100">
          {{ formatMoney(item ? Number(item.price) + extrasTotal : 0, 'EGP') }}
          <span v-if="extrasTotal > 0" class="text-xs font-normal text-gray-500 dark:text-gray-400">({{ t('backoffice.extrasSelection.extrasAmount', { amount: formatMoney(extrasTotal, 'EGP') }) }})</span>
        </div>
        <div class="flex gap-2">
          <AppButton variant="ghost" @click="emit('close')">{{ t('backoffice.extrasSelection.cancel') }}</AppButton>
          <AppButton variant="primary" :disabled="!canConfirm" @click="confirm">{{ t('backoffice.extrasSelection.add') }}</AppButton>
        </div>
      </div>
    </template>
  </AppModal>
</template>
