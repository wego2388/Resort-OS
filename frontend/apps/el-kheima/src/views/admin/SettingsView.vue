<script setup lang="ts">
// SettingsView — إدارة إعدادات الفرع (admin فقط، مطابق لبوابة الراوتر requiredRole: 'admin')
//
// Endpoints حقيقية من core/api/router.py:
//   GET /api/v1/settings?branch_id=X       ← قائمة الإعدادات (crud.list_settings يفلتر بالمطابقة
//                                             التامة لـ branch_id، من غير fallback للعام/global هنا)
//   PUT /api/v1/settings/{key}?branch_id=X ← upsert (يُنشئ لو مش موجود، يُحدّث لو موجود) — get_admin_user
//
// كل الإعدادات هنا مربوطة بالفرع الحالي (نفس نمط باقي شاشات admin) — إعداد
// "عام" (branch_id=null) مش هيظهر في القايمة إلا لو اتعمله PUT بدون branch_id.
//
// Gate 2B3A: الكتابة (PUT) بقت محتاجة step-up token صالح (X-Step-Up-Token) +
// reason إجباري — راجع StepUpConfirmModal.vue وdocs/audits/
// gate-2b3a-step-up-control-plane.md. auth.branchId العام لسه بيرجع 1
// افتراضيًا لأي حساب (مفيش عمود branch_id حقيقي على User خالص — قرار
// معماري أكبر مؤجَّل، راجع CLAUDE.md §18) — هنا بس بنعرض تحذير واضح بدل
// ما نفترض بصمت إن branch=1 صح دايمًا؛ مفيش تغيير على auth.branchId نفسه
// ولا على أي شاشة تانية بتستخدمه (خارج نطاق Gate 2B3A).
import { ref, reactive, computed, onMounted } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppButton, AppInput, AppBadge, AppSpinner, EmptyState, useToast } from '@resort-os/ui'
import { useI18n } from 'vue-i18n'
import StepUpConfirmModal from '../../components/StepUpConfirmModal.vue'

const { t, locale } = useI18n()
const { formatDateTime } = useStaffFormat()
const toast = useToast()
const auth = useAuthStore()
const branchId = auth.branchId
// حساب بلا branch_id حقيقي في استجابة /auth/me — تحذير بس، مش حظر (نفس
// السلوك القديم فعليًا لسه شغال، بدون ادّعاء إنه صحيح 100%).
const hasRealBranchContext = computed(() => auth.user?.branch_id != null)

// روابط سريعة لأقسام الإدارة ذات الصلة
const QUICK_LINKS = [
  { path: '/admin/tables', labelKey: 'backoffice.settings.quickLinkTables', icon: '🪑', color: 'bg-orange-50 border-orange-200 hover:bg-orange-100 dark:bg-orange-950/40 dark:border-orange-900 dark:hover:bg-orange-950/60' },
  { path: '/admin/cafe-menu', labelKey: 'backoffice.settings.quickLinkCafeMenu', icon: '☕', color: 'bg-cyan-50 border-cyan-200 hover:bg-cyan-100 dark:bg-cyan-950/40 dark:border-cyan-900 dark:hover:bg-cyan-950/60' },
  { path: '/admin/menu', labelKey: 'backoffice.settings.quickLinkRestaurantMenu', icon: '🍽️', color: 'bg-amber-50 border-amber-200 hover:bg-amber-100 dark:bg-amber-950/40 dark:border-amber-900 dark:hover:bg-amber-950/60' },
  { path: '/admin/qr', labelKey: 'backoffice.nav.qrCodes', icon: '📱', color: 'bg-blue-50 border-blue-200 hover:bg-blue-100 dark:bg-blue-950/40 dark:border-blue-900 dark:hover:bg-blue-950/60' },
]

// شرح كل مفتاح إعداد معروف — اتبنى بقراءة الكود فعليًا (مش تخمين)، راجع مين
// بيقرا كل key بالظبط قبل ما تضيف/تعدّل سطر هنا:
//   - beach.price.* → app/modules/beach/services.py::_get_base_prices()
//   - no_show_deadline_hour → app/tasks/pms_tasks.py::process_no_shows()
//   - الباقي (vat_percentage, service_charge_percentage, default_currency,
//     timezone, beach.capacity_max, no_show_policy,
//     discount_approval_threshold) — القيمة الفعلية دايمًا بتتاخد من متغيرات
//     بيئة السيرفر (.env) أو من عمود تاني في الداتابيز، مش من الصف ده — تعديله
//     من هنا مالوش أي أثر تشغيلي حاليًا (اتأكد بالبحث في الكود كله، مش افتراض).
interface SettingMeta {
  description: { ar: string; en: string }
  /** live = القيمة دي فعلاً بتتقرا وبتأثر على سلوك النظام فورًا عند الحفظ */
  live: boolean
}

const SETTINGS_META: Record<string, SettingMeta> = {
  'beach.price.adult': {
    description: {
      ar: 'سعر تذكرة دخول الشاطئ للبالغ (جنيه) — يُستخدم فعليًا في تسعير كل عملية بيع بشاشة كاشير الشاطئ، فوق أي نسبة ذروة (surge) على المكان.',
      en: 'Adult beach-entry ticket price (EGP) — actually used to price every sale at the beach cashier screen, on top of any location surge rate.',
    },
    live: true,
  },
  'beach.price.child': {
    description: {
      ar: 'سعر تذكرة دخول الشاطئ للطفل (جنيه) — يُستخدم فعليًا عند بيع تذكرة طفل بكاشير الشاطئ.',
      en: "Child beach-entry ticket price (EGP) — actually used when selling a child's ticket at the beach cashier.",
    },
    live: true,
  },
  'beach.price.resident': {
    description: {
      ar: 'سعر تذكرة دخول الشاطئ للمقيم/صاحب الاشتراك (جنيه) — يُستخدم فعليًا عند اختيار نوع تذكرة "مقيم" بكاشير الشاطئ.',
      en: 'Resident/subscriber beach-entry ticket price (EGP) — actually used when selecting a "resident" ticket type at the beach cashier.',
    },
    live: true,
  },
  'beach.price.towel': {
    description: {
      ar: 'سعر إيجار المنشفة (جنيه) — يُضاف على سعر تذكرة الكبير فعليًا عند اختيار "دخول + منشفة" بكاشير الشاطئ.',
      en: 'Towel rental price (EGP) — actually added to the adult ticket price when "entry + towel" is selected at the beach cashier.',
    },
    live: true,
  },
  no_show_deadline_hour: {
    description: {
      ar: 'الساعة (بتوقيت المنتجع، بالأرقام فقط من 0 لـ23 — مثلاً 18 يعني 6 مساءً) اللي بعدها الحجوزات المؤكدة اللي محدش وصلها بتتحول تلقائيًا لـ"لم يحضر". بتتفحص كل ساعة عبر مهمة مجدولة فعلية.',
      en: 'The hour (resort time, 0–23 — e.g. 18 means 6 PM) after which confirmed bookings nobody arrived for are automatically marked "no-show". Checked hourly by a real scheduled task.',
    },
    live: true,
  },
  vat_percentage: {
    description: {
      ar: 'نسبة ضريبة القيمة المضافة. تنبيه: النسبة الفعلية المُطبَّقة على كل الفواتير بتتحدد من إعداد سيرفر منفصل (متغير بيئة)، مش من هنا — تعديل القيمة دي حاليًا بلا أي أثر على الحسابات الفعلية.',
      en: 'VAT percentage. Note: the rate actually applied to every invoice is set by a separate server-side (environment variable) setting, not this one — editing this value currently has no effect on real calculations.',
    },
    live: false,
  },
  service_charge_percentage: {
    description: {
      ar: 'نسبة رسم الخدمة. تنبيه: النسبة الفعلية المُطبَّقة بتتحدد من إعداد سيرفر منفصل (متغير بيئة)، مش من هنا — تعديل القيمة دي حاليًا بلا أي أثر على الحسابات الفعلية.',
      en: 'Service charge percentage. Note: the rate actually applied is set by a separate server-side (environment variable) setting, not this one — editing this value currently has no effect on real calculations.',
    },
    live: false,
  },
  default_currency: {
    description: {
      ar: 'رمز العملة الافتراضية (مثل EGP). تنبيه: العملة الفعلية المستخدمة في النظام بتتحدد من إعداد سيرفر منفصل (متغير بيئة)، مش من هنا.',
      en: 'Default currency code (e.g. EGP). Note: the currency actually used by the system is set by a separate server-side (environment variable) setting, not this one.',
    },
    live: false,
  },
  timezone: {
    description: {
      ar: 'المنطقة الزمنية للمنتجع (مثل Africa/Cairo). تنبيه: كل حسابات "النهاردة/دلوقتي" في النظام بتستخدم إعداد سيرفر منفصل (متغير بيئة)، مش القيمة دي — تعديلها من هنا بلا أثر.',
      en: 'The resort\'s timezone (e.g. Africa/Cairo). Note: every "today/now" calculation in the system uses a separate server-side (environment variable) setting, not this value — editing it here has no effect.',
    },
    live: false,
  },
  'beach.capacity_max': {
    description: {
      ar: 'أقصى سعة استيعابية للشاطئ. تنبيه: السعة الفعلية المُستخدمة في التشغيل بتتحدد من بيانات مخزون الشاطئ في الداتابيز، مش من هنا — تعديل القيمة دي حاليًا بلا أثر.',
      en: 'Maximum beach capacity. Note: the capacity actually used in operations comes from the beach inventory data in the database, not this — editing this value currently has no effect.',
    },
    live: false,
  },
  no_show_policy: {
    description: {
      ar: 'سياسة التعامل مع عدم الحضور (نص وصفي فقط). تنبيه: مفيش كود حاليًا بيقرأ القيمة دي أو يغيّر سلوكه بناءً عليها — كل حجز يتأخر عن الموعد بيتحول لـ"لم يحضر" بنفس الطريقة بغض النظر عن القيمة هنا.',
      en: 'No-show handling policy (descriptive text only). Note: no code currently reads this value or changes behavior based on it — every late booking is marked "no-show" the same way regardless of this value.',
    },
    live: false,
  },
  discount_approval_threshold: {
    description: {
      ar: 'حد قيمة الخصم اللي (نظريًا) محتاج موافقة إضافية. تنبيه: مفيش كود حاليًا في محرك الخصومات بيقرأ أو يُفعّل هذا الحد — القيمة معلوماتية فقط دلوقتي.',
      en: 'The discount value threshold that (theoretically) requires extra approval. Note: no code in the discount engine currently reads or enforces this threshold — informational only for now.',
    },
    live: false,
  },
}

function settingMeta(key: string) {
  return SETTINGS_META[key] ?? null
}

function settingDescription(key: string): string {
  const meta = settingMeta(key)
  if (!meta) return ''
  return locale.value === 'ar' ? meta.description.ar : meta.description.en
}

// Gate 3A: formatting centralized in useStaffFormat (locale-aware, tabular
// Latin digits). Prior Codex fix (2026-07-18) made the tag follow the UI
// locale; this now routes through the shared utility instead of an inline tag.
function formatUpdatedAt(iso: string): string {
  return formatDateTime(iso)
}

interface SettingRow {
  id:         number
  key:        string
  value:      string
  branch_id:  number | null
  updated_at: string
}

const settings   = ref<SettingRow[]>([])
const loading    = ref(true)
const loadError  = ref('')
const edited     = reactive<Record<string, string>>({})
const savingKey  = ref<string | null>(null)

const newKey    = ref('')
const newValue  = ref('')
const creating  = ref(false)

// Gate 2B3A — step-up state لعملية الحفظ/الإنشاء الجارية دلوقتي (واحدة بس
// ممكن تكون مفتوحة في نفس اللحظة، زي PinGuardModal بالظبط)
interface PendingStepUp {
  kind: 'save' | 'create'
  key: string
  value: string
  row?: SettingRow
}
const pendingStepUp = ref<PendingStepUp | null>(null)
const stepUpError = ref('')
const stepUpBusy = ref(false)

function isDirty(row: SettingRow) {
  return edited[row.key] !== undefined && edited[row.key] !== row.value
}

async function loadSettings() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.get(ENDPOINTS.settings.get, { params: { branch_id: branchId } })
    settings.value = res.data
    for (const row of res.data as SettingRow[]) {
      edited[row.key] = row.value
    }
  } catch {
    loadError.value = t('backoffice.settings.loadError')
  } finally {
    loading.value = false
  }
}

function requestSave(row: SettingRow) {
  const value = edited[row.key] ?? row.value
  stepUpError.value = ''
  pendingStepUp.value = { kind: 'save', key: row.key, value, row }
}

function requestCreate() {
  const key = newKey.value.trim()
  if (!key) {
    toast.error(t('backoffice.settings.keyRequired'))
    return
  }
  if (settings.value.some((s) => s.key === key)) {
    toast.error(t('backoffice.settings.keyExists', { key }))
    return
  }
  stepUpError.value = ''
  pendingStepUp.value = { kind: 'create', key, value: newValue.value }
}

async function onStepUpConfirmed({ stepUpToken, reason }: { stepUpToken: string; reason: string }) {
  const pending = pendingStepUp.value
  if (!pending) return
  stepUpBusy.value = true
  if (pending.kind === 'save') savingKey.value = pending.key
  else creating.value = true

  try {
    const res = await api.put(
      ENDPOINTS.settings.set(pending.key),
      { value: pending.value, reason },
      { params: { branch_id: branchId }, headers: { 'X-Step-Up-Token': stepUpToken } },
    )
    const updated: SettingRow = res.data
    const idx = settings.value.findIndex((s) => s.key === updated.key)
    if (idx !== -1) settings.value[idx] = updated
    else settings.value = [...settings.value, updated].sort((a, b) => a.key.localeCompare(b.key))
    edited[updated.key] = updated.value

    if (pending.kind === 'save') {
      toast.success(t('backoffice.settings.toastSaved', { key: pending.key }))
    } else {
      toast.success(t('backoffice.settings.toastCreated', { key: pending.key }))
      newKey.value = ''
      newValue.value = ''
    }
    pendingStepUp.value = null
  } catch (e: any) {
    const code = e?.response?.data?.detail?.error_code
    if (code === 'STEP_UP_INVALID') {
      // Gate 2B3A: الإثبات اتستخدم/انتهى — تبدأ دورة إثبات جديدة، مفيش
      // إعادة إرسال تلقائي للطلب الفعلي.
      stepUpError.value = t('backoffice.stepUp.errorInvalidRestart')
    } else {
      const message = pending.kind === 'save'
        ? t('backoffice.settings.toastErrorSave', { key: pending.key })
        : t('backoffice.settings.toastErrorCreate')
      toast.error(e?.response?.data?.detail?.message ?? message)
      pendingStepUp.value = null
    }
  } finally {
    stepUpBusy.value = false
    savingKey.value = null
    creating.value = false
  }
}

function cancelStepUp() {
  pendingStepUp.value = null
  stepUpError.value = ''
}

const stepUpDescription = computed(() => {
  const pending = pendingStepUp.value
  if (!pending) return ''
  return pending.kind === 'save'
    ? t('backoffice.settings.reasonPromptSave', { key: pending.key })
    : t('backoffice.settings.reasonPromptCreate', { key: pending.key })
})
const stepUpIntent = computed(() => {
  const pending = pendingStepUp.value
  if (!pending) return {}
  return { key: pending.key, branch_id: branchId, value: pending.value }
})

onMounted(loadSettings)
</script>

<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ t('backoffice.settings.title') }}</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.settings.subtitle') }}</p>
    </div>

    <div v-if="!hasRealBranchContext" class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
      ⚠️ {{ t('backoffice.settings.branchContextWarning') }}
    </div>

    <!-- روابط سريعة لأقسام الإدارة ذات الصلة -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <router-link v-for="link in QUICK_LINKS" :key="link.path" :to="link.path"
        :class="['flex items-center gap-2 p-3 rounded-xl border-2 transition-colors text-sm font-semibold text-gray-700 dark:text-gray-300', link.color]"
      >
        <span class="text-xl">{{ link.icon }}</span>
        {{ t(link.labelKey) }}
      </router-link>
    </div>

    <div v-if="loadError" class="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
      <span>⚠️ {{ loadError }}</span>
      <button @click="loadSettings" class="font-semibold underline hover:no-underline">{{ t('backoffice.settings.retry') }}</button>
    </div>

    <!-- إضافة إعداد جديد -->
    <AppCard :title="t('backoffice.settings.addNewTitle')">
      <div class="flex flex-col md:flex-row md:items-end gap-3">
        <div class="flex-1">
          <AppInput v-model="newKey" :label="t('backoffice.settings.keyLabel')" :placeholder="t('backoffice.settings.keyPlaceholder')" :disabled="creating" />
        </div>
        <div class="flex-1">
          <AppInput v-model="newValue" :label="t('backoffice.settings.valueLabel')" :placeholder="t('backoffice.settings.valuePlaceholder')" :disabled="creating" />
        </div>
        <AppButton variant="primary" :loading="creating" @click="requestCreate">{{ t('backoffice.settings.addButton') }}</AppButton>
      </div>
    </AppCard>

    <!-- قائمة الإعدادات -->
    <AppCard :title="t('backoffice.settings.currentSettingsTitle')" padding="none">
      <div v-if="loading" class="p-10 flex justify-center">
        <AppSpinner size="lg" />
      </div>
      <EmptyState
        v-else-if="settings.length === 0"
        icon="⚙️"
        :title="t('backoffice.settings.noSettingsTitle')"
        :subtitle="t('backoffice.settings.noSettingsSubtitle')"
      />
      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.settings.colKey') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.settings.colValue') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.settings.colUpdatedAt') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.settings.colAction') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in settings" :key="row.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 align-top pt-4 max-w-[320px]">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-sm text-gray-800 dark:text-gray-200">{{ row.key }}</span>
                  <AppBadge v-if="settingMeta(row.key)" size="sm" :variant="settingMeta(row.key)!.live ? 'success' : 'neutral'">
                    {{ settingMeta(row.key)!.live ? t('backoffice.settings.live') : t('backoffice.settings.noEffect') }}
                  </AppBadge>
                </div>
                <p v-if="settingMeta(row.key)" class="text-xs text-gray-400 dark:text-gray-400 mt-1">
                  {{ settingDescription(row.key) }}
                </p>
                <p v-else class="text-xs text-gray-400 dark:text-gray-400 mt-1">
                  {{ t('backoffice.settings.customSettingNote') }}
                </p>
              </td>
              <td class="px-4 py-3 min-w-[240px]">
                <AppInput v-model="edited[row.key]" :disabled="savingKey === row.key" />
              </td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 align-top pt-4">
                {{ formatUpdatedAt(row.updated_at) }}
              </td>
              <td class="px-4 py-3 align-top">
                <AppButton
                  variant="primary"
                  size="sm"
                  :loading="savingKey === row.key"
                  :disabled="!isDirty(row) || savingKey === row.key"
                  @click="requestSave(row)"
                >
                  {{ t('backoffice.settings.save') }}
                </AppButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <StepUpConfirmModal
      v-if="pendingStepUp"
      :purpose="'setting_upsert'"
      :intent="stepUpIntent"
      :description="stepUpDescription"
      :loading="stepUpBusy"
      :error-message="stepUpError"
      @confirmed="onStepUpConfirmed"
      @cancel="cancelStepUp"
    />
  </div>
</template>
