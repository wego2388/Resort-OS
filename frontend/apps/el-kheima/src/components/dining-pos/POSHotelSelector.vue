<script setup lang="ts">
/**
 * POSHotelSelector.vue — اختيار الفندق المتعاقد على طلب الدايننج.
 *
 * الكاشير/الويتر يضغط على "＋ فندق" في الكارت ويختار من قائمة الفنادق
 * المتعاقدة النشطة. الاختيار اختياري تمامًا — معظم الطلبات عادية.
 * بيتعمل lazy load لقائمة الفنادق أول مرة يُفتح فيها الـ selector.
 *
 * الـ dropdown بيتعمل له Teleport to body مع حساب position حقيقي من
 * bounding rect الزرار — عشان يظهر تحته بالظبط حتى جوه scroll containers.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { LoadingState } from '@resort-os/ui'
import type { B2BContractOption } from './types'

const props = defineProps<{
  branchId: number | null
  selectedContractId: number | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [contract: B2BContractOption | null]
}>()

const { t } = useI18n()
const { name } = useStaffFormat()

const open = ref(false)
const contracts = ref<B2BContractOption[]>([])
const loading = ref(false)
const loaded = ref(false)

// ref للزرار لحساب الـ position الحقيقية
const triggerRef = ref<HTMLButtonElement | null>(null)
const dropdownStyle = ref<{ top: string; left: string; width: string }>({
  top: '0px',
  left: '0px',
  width: '240px',
})

function contractDisplayName(c: B2BContractOption): string {
  return name({ name: c.hotel_name, name_ar: c.hotel_name_ar })
}

const selectedContract = computed(() =>
  contracts.value.find(c => c.id === props.selectedContractId) ?? null,
)

async function loadContracts() {
  if (loaded.value || loading.value || !props.branchId) return
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.dining.b2bContracts, {
      params: { branch_id: props.branchId },
    })
    contracts.value = data
    loaded.value = true
  } catch {
    // فشل التحميل — الـ dropdown بيفضل فاضي، مش كارثة
  } finally {
    loading.value = false
  }
}

function calculateDropdownPosition() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.bottom
  const spaceAbove = rect.top
  const dropdownHeight = 260 // max-h تقريبية

  // لو مفيش مساحة تحت، نعرض فوق
  const showAbove = spaceBelow < dropdownHeight && spaceAbove > spaceBelow
  dropdownStyle.value = {
    top: showAbove
      ? `${rect.top + window.scrollY - dropdownHeight - 4}px`
      : `${rect.bottom + window.scrollY + 4}px`,
    left: `${rect.left + window.scrollX}px`,
    width: `${Math.max(rect.width, 240)}px`,
  }
}

function toggle() {
  if (props.disabled) return
  if (!open.value) {
    calculateDropdownPosition()
    loadContracts()
  }
  open.value = !open.value
}

function select(contract: B2BContractOption | null) {
  emit('select', contract)
  open.value = false
}

watch(() => props.branchId, () => {
  loaded.value = false
  contracts.value = []
})

function onDocClick(e: MouseEvent) {
  const target = e.target as Element | null
  if (!target?.closest?.('.pos-hotel-selector') && !target?.closest?.('.pos-hotel-dropdown')) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="pos-hotel-selector relative">
    <button
      ref="triggerRef"
      type="button"
      :disabled="disabled"
      :class="[
        'w-full min-h-[44px] rounded-xl border px-3 py-2 text-start transition-colors flex items-center justify-between gap-2',
        selectedContractId
          ? 'border-primary-400 bg-primary-50/60 dark:bg-primary-950/20'
          : 'border-dashed border-stone-300 dark:border-border hover:border-primary-400',
        disabled && 'opacity-60 cursor-not-allowed',
      ]"
      @click.stop="toggle"
    >
      <div class="min-w-0">
        <template v-if="selectedContract">
          <div class="text-xs text-primary-700 dark:text-primary-300 font-semibold">
            🏨 {{ t('backoffice.pos.hotel.attached') }}
          </div>
          <div class="font-bold text-gray-900 dark:text-gray-100 truncate">
            {{ contractDisplayName(selectedContract) }}
          </div>
        </template>
        <template v-else>
          <div class="font-bold text-gray-500 dark:text-gray-400">
            🏨 {{ t('backoffice.pos.hotel.add') }}
          </div>
          <div class="text-xs text-gray-400 mt-0.5">{{ t('backoffice.pos.hotel.addHint') }}</div>
        </template>
      </div>
      <span v-if="selectedContract" class="text-primary-700 dark:text-primary-300 text-sm font-bold flex-shrink-0">
        {{ t('backoffice.pos.hotel.change') }}
      </span>
    </button>

    <!-- Dropdown — Teleport to body مع position محسوبة من bounding rect -->
    <Teleport to="body">
      <div
        v-if="open"
        class="pos-hotel-dropdown fixed z-50 rounded-2xl bg-white dark:bg-surface border border-stone-200 dark:border-border shadow-2xl p-3 max-h-64 overflow-y-auto"
        :style="dropdownStyle"
      >
        <LoadingState v-if="loading" size="sm" :label="t('backoffice.pos.hotel.loading')" />
        <template v-else>
          <!-- إلغاء الاختيار -->
          <button
            v-if="selectedContractId"
            type="button"
            class="w-full text-start px-3 py-2 rounded-xl text-sm text-danger hover:bg-danger/10 font-semibold mb-1"
            @click="select(null)"
          >
            ✕ {{ t('backoffice.pos.hotel.clear') }}
          </button>
          <div v-if="contracts.length === 0 && !loading" class="text-sm text-gray-400 text-center py-4">
            {{ t('backoffice.pos.hotel.empty') }}
          </div>
          <button
            v-for="contract in contracts"
            :key="contract.id"
            type="button"
            :class="[
              'w-full text-start px-3 py-2.5 rounded-xl transition-colors font-semibold text-sm',
              contract.id === selectedContractId
                ? 'bg-primary-50 dark:bg-primary-950/30 text-primary-800 dark:text-primary-300'
                : 'hover:bg-stone-100 dark:hover:bg-gray-800 text-gray-800 dark:text-gray-200',
            ]"
            @click="select(contract)"
          >
            🏨 {{ contractDisplayName(contract) }}
          </button>
        </template>
      </div>
    </Teleport>
  </div>
</template>
