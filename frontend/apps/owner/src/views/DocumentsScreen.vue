<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AppIcon } from '@resort-os/ui'
import { downloadOwnerDocument, fetchOwnerDocuments } from '../api/owner'
import type { OwnerDocument } from '../api/types'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'

const documents = ref<OwnerDocument[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const downloadingId = ref<string | null>(null)

const typeLabels: Record<string, string> = {
  commercial_register: 'السجل التجاري',
  tourism_license: 'ترخيص السياحة',
  fire_permit: 'تصريح الحماية المدنية',
  health_certificate: 'شهادة صحية',
  building_permit: 'ترخيص مبانٍ',
  liquor_license: 'ترخيص مشروبات',
  insurance_property: 'تأمين المنشأة',
  supplier_contract: 'عقد مورد',
  lease_agreement: 'عقد إيجار',
  bank_account_docs: 'مستندات بنكية',
  other_branch: 'مستند آخر',
}

const urgentCount = computed(() => documents.value.filter(document => (
  document.days_until_expiry != null && document.days_until_expiry <= 7
)).length)

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(`${value}T12:00:00`)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} كيلوبايت`
  return `${(bytes / (1024 * 1024)).toFixed(1)} ميجابايت`
}

function expiryLabel(document: OwnerDocument): string {
  const days = document.days_until_expiry
  if (days == null) return 'بلا تاريخ انتهاء'
  if (days < 0) return `منتهي منذ ${Math.abs(days)} يوم`
  if (days === 0) return 'ينتهي اليوم'
  return `متبقي ${days} يوم`
}

function expiryClass(document: OwnerDocument): string {
  const days = document.days_until_expiry
  if (days == null || days > 30) return 'text-owner-muted border-owner-border'
  if (days <= 7) return 'text-owner-red border-owner-red/30 bg-owner-red/10'
  return 'text-owner-amber border-owner-amber/30 bg-owner-amber/10'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchOwnerDocuments({
      search: search.value.trim() || undefined,
      size: 100,
    })
    documents.value = data.items
  } catch {
    error.value = 'تعذّر تحميل المستندات الآمنة. تحقق من الاتصال ثم حاول مرة أخرى.'
  } finally {
    loading.value = false
  }
}

async function download(document: OwnerDocument) {
  downloadingId.value = document.id
  try {
    await downloadOwnerDocument(document.id, document.original_filename)
  } catch {
    error.value = 'تعذّر التحقق من سلامة الملف أو تنزيله.'
  } finally {
    downloadingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="flex-1 overflow-y-auto overscroll-contain">
    <div class="mx-auto max-w-5xl space-y-4 p-4 pb-6">
      <section class="owner-card" aria-labelledby="documents-title">
        <div class="flex items-start gap-3">
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-owner-green/10 text-owner-green">
            <AppIcon name="archive" size="lg" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 id="documents-title" class="text-lg font-black text-owner-text">مستندات المنشأة</h2>
            <p class="mt-1 text-xs leading-5 text-owner-muted">
              تظهر هنا فقط الوثائق التي صنّفتها الإدارة «متاحة للمالك». التنزيل مشفّر ومحمي بجلسة الدخول.
            </p>
          </div>
        </div>
        <div v-if="urgentCount" class="mt-4 flex min-h-12 items-center gap-2 rounded-xl border border-owner-red/30 bg-owner-red/10 px-3 text-sm font-bold text-owner-red">
          <AppIcon name="warning" />
          {{ urgentCount }} مستند يحتاج متابعة عاجلة
        </div>
        <form class="relative mt-4" role="search" @submit.prevent="load">
          <label for="owner-document-search" class="sr-only">البحث في المستندات</label>
          <input
            id="owner-document-search"
            v-model="search"
            type="search"
            placeholder="ابحث بعنوان المستند..."
            class="min-h-12 w-full rounded-xl border border-owner-border bg-owner-bg px-4 pe-14 text-sm text-owner-text outline-none focus:border-owner-green"
          />
          <button
            type="submit"
            class="touch-target absolute end-0 top-0 text-owner-muted active:text-owner-green"
            aria-label="تنفيذ البحث"
            :disabled="loading"
          >
            <AppIcon name="search" />
          </button>
        </form>
      </section>

      <ErrorState v-if="error && !loading" :message="error" @retry="load" />
      <SkeletonCards v-else-if="loading" />
      <div v-else-if="documents.length === 0" class="owner-card py-10 text-center">
        <AppIcon name="document" size="xl" class="mx-auto text-owner-muted" />
        <p class="mt-3 font-bold text-owner-text">لا توجد مستندات متاحة حاليًا</p>
        <p class="mt-1 text-xs text-owner-muted">عندما تتيح الإدارة مستندًا للمالك سيظهر هنا تلقائيًا.</p>
      </div>
      <section v-else class="grid gap-3 sm:grid-cols-2" aria-label="قائمة مستندات المنشأة">
        <article v-for="document in documents" :key="document.id" class="owner-card flex flex-col gap-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="break-words font-bold text-owner-text">{{ document.title }}</h3>
              <p class="mt-1 text-xs text-owner-muted">{{ typeLabels[document.doc_type] ?? document.doc_type }}</p>
            </div>
            <span class="shrink-0 rounded-full border px-2 py-1 text-[11px] font-bold" :class="expiryClass(document)">
              {{ expiryLabel(document) }}
            </span>
          </div>
          <p v-if="document.description" class="line-clamp-2 text-xs leading-5 text-owner-muted">
            {{ document.description }}
          </p>
          <dl class="grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt class="text-owner-muted">تاريخ الإصدار</dt>
              <dd class="mt-1 font-semibold text-owner-text">{{ formatDate(document.issue_date) }}</dd>
            </div>
            <div>
              <dt class="text-owner-muted">حجم الملف</dt>
              <dd class="mt-1 font-semibold text-owner-text">{{ formatSize(document.size_bytes) }}</dd>
            </div>
          </dl>
          <button
            type="button"
            class="mt-auto flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-owner-green px-4 font-bold text-black active:opacity-70 disabled:opacity-50"
            :disabled="downloadingId === document.id"
            @click="download(document)"
          >
            <AppIcon name="download" />
            {{ downloadingId === document.id ? 'جارِ التحقق...' : 'تنزيل آمن' }}
          </button>
        </article>
      </section>
    </div>
  </div>
</template>
