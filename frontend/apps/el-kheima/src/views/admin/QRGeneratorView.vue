<script setup lang="ts">
/** Gate 8 QR administration: one locally-rendered QR per physical table. */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

interface Table {
  id: number
  table_number: string
  section: string | null
  status: string
}

interface LocationToken {
  id: number
  token: string
  branch_id: number
  location_type: 'dining_table'
  location_id: number
  is_active: boolean
  created_at: string
}

const route = useRoute()
const auth = useAuthStore()
const toast = useToast()
const { locale, t } = useI18n()

const branchId = computed(() => auth.branchId)
const publicBase = computed(() => {
  const configured = (import.meta.env.VITE_PUBLIC_SITE_URL as string | undefined)?.replace(/\/$/, '')
  if (configured) return configured
  return window.location.origin.replace(':5173', ':5174').replace(':5175', ':5174')
})

const tables = ref<Table[]>([])
const tokens = ref<LocationToken[]>([])
const selectedIds = ref<Set<number>>(new Set())
const canvasRefs = ref<Record<number, HTMLCanvasElement | null>>({})
const loading = ref(false)
const mutatingId = ref<number | null>(null)

const tokenByTable = computed(() => new Map(tokens.value.map(row => [row.location_id, row])))
const grouped = computed(() => {
  const map = new Map<string, Table[]>()
  for (const table of tables.value) {
    const key = table.section || t('backoffice.qrGenerator.general')
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(table)
  }
  return Array.from(map.entries())
})

function guestUrl(tableId: number): string | null {
  const token = tokenByTable.value.get(tableId)?.token
  return token ? `${publicBase.value}/s/${encodeURIComponent(token)}` : null
}

async function renderTableQr(tableId: number) {
  const canvas = canvasRefs.value[tableId]
  const url = guestUrl(tableId)
  if (!canvas || !url) return
  await QRCode.toCanvas(canvas, url, {
    width: 192,
    margin: 2,
    errorCorrectionLevel: 'M',
    color: { dark: '#111827', light: '#ffffff' },
  })
}

async function renderAll() {
  await nextTick()
  await Promise.all(tables.value.map(table => renderTableQr(table.id)))
}

async function loadData() {
  if (!branchId.value) return
  loading.value = true
  try {
    const [tablesResponse, tokensResponse] = await Promise.all([
      api.get(ENDPOINTS.dining.tables(branchId.value)),
      api.get('/api/v1/service-location-tokens', { params: { branch_id: branchId.value } }),
    ])
    const tableData = tablesResponse.data
    tables.value = tableData.tables ?? tableData.items ?? tableData ?? []
    tokens.value = (tokensResponse.data ?? []).filter(
      (row: LocationToken) => row.location_type === 'dining_table' && row.is_active,
    )
    await renderAll()
  } catch (error: any) {
    toast.error(error?.response?.data?.detail ?? t('backoffice.qrGenerator.msg.loadTablesError'))
  } finally {
    loading.value = false
  }
}

async function mintOrRotate(table: Table, rotate = false) {
  if (!branchId.value || mutatingId.value !== null) return
  if (rotate && !window.confirm(t('backoffice.qrGenerator.rotateConfirm', { number: table.table_number }))) return
  mutatingId.value = table.id
  try {
    const { data } = await api.post('/api/v1/service-location-tokens', {
      branch_id: branchId.value,
      location_type: 'dining_table',
      location_id: table.id,
    })
    tokens.value = [...tokens.value.filter(row => row.location_id !== table.id), data]
    await renderTableQr(table.id)
    toast.success(t(rotate ? 'backoffice.qrGenerator.msg.rotated' : 'backoffice.qrGenerator.msg.generated'))
  } catch (error: any) {
    toast.error(error?.response?.data?.detail ?? t('backoffice.qrGenerator.msg.generateError'))
  } finally {
    mutatingId.value = null
  }
}

async function generateSelectedMissing() {
  for (const table of tables.value) {
    if (selectedIds.value.has(table.id) && !tokenByTable.value.has(table.id)) {
      await mintOrRotate(table)
    }
  }
}

function toggleSelect(id: number) {
  const next = new Set(selectedIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedIds.value = next
}

function selectAll() {
  selectedIds.value = new Set(tables.value.map(table => table.id))
}

function clearAll() {
  selectedIds.value = new Set()
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char] as string)
}

async function printSelected() {
  const selected = tables.value.filter(table => selectedIds.value.has(table.id))
  if (!selected.length) {
    toast.error(t('backoffice.qrGenerator.msg.selectAtLeastOneTable'))
    return
  }
  const missing = selected.filter(table => !guestUrl(table.id))
  if (missing.length) {
    toast.error(t('backoffice.qrGenerator.msg.generateBeforePrint', { count: missing.length }))
    return
  }
  const cards = await Promise.all(selected.map(async table => ({
    table,
    dataUrl: await QRCode.toDataURL(guestUrl(table.id)!, { width: 500, margin: 2, errorCorrectionLevel: 'M' }),
  })))
  const dir = locale.value === 'ar' ? 'rtl' : 'ltr'
  const html = `<!doctype html><html dir="${dir}" lang="${locale.value}"><head><meta charset="UTF-8"><title>${escapeHtml(t('backoffice.qrGenerator.printTitle'))}</title><style>
    body{font-family:Arial,sans-serif;margin:0;padding:20px;background:#fff}.grid{display:flex;flex-wrap:wrap;gap:20px;justify-content:center}.card{border:2px solid #d4a017;border-radius:16px;padding:20px;text-align:center;width:220px;page-break-inside:avoid}.card img{width:190px;height:190px}.name{font-size:20px;font-weight:900;margin-top:10px}.section{font-size:12px;color:#6b7280;margin-top:4px}@media print{body{padding:8px}}
  </style></head><body><div class="grid">${cards.map(({ table, dataUrl }) => `<div class="card"><img src="${dataUrl}" alt="QR"><div class="name">${escapeHtml(t('backoffice.qrGenerator.tableNumber', { number: table.table_number }))}</div>${table.section ? `<div class="section">${escapeHtml(table.section)}</div>` : ''}</div>`).join('')}</div></body></html>`
  const win = window.open('', '_blank')
  if (!win) {
    toast.error(t('backoffice.qrGenerator.msg.popupBlocked'))
    return
  }
  win.document.write(html)
  win.document.close()
  win.focus()
  window.setTimeout(() => win.print(), 300)
}

async function downloadQr(table: Table) {
  const url = guestUrl(table.id)
  if (!url) {
    toast.error(t('backoffice.qrGenerator.msg.generateBeforeDownload'))
    return
  }
  const dataUrl = await QRCode.toDataURL(url, { width: 700, margin: 2, errorCorrectionLevel: 'M' })
  const anchor = document.createElement('a')
  anchor.href = dataUrl
  anchor.download = `service-table-${table.table_number}.png`
  anchor.click()
}

onMounted(async () => {
  await loadData()
  const highlighted = Number(route.query.highlight)
  if (Number.isInteger(highlighted) && highlighted > 0) {
    selectedIds.value = new Set([highlighted])
    await nextTick()
    document.getElementById(`table-card-${highlighted}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
})
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-black text-gray-900 dark:text-gray-100">📱 {{ t('backoffice.qrGenerator.title') }}</h1>
        <p class="text-xs text-gray-500 mt-1 dark:text-gray-400">{{ t('backoffice.qrGenerator.subtitle') }}</p>
      </div>
      <div class="flex gap-2 flex-wrap">
        <button class="px-3 py-2 bg-stone-100 rounded-lg text-sm font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200" @click="selectAll">{{ t('backoffice.qrGenerator.selectAll') }}</button>
        <button class="px-3 py-2 bg-stone-100 rounded-lg text-sm font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200" @click="clearAll">{{ t('backoffice.qrGenerator.clearSelection') }}</button>
        <button class="px-3 py-2 bg-amber-100 text-amber-800 rounded-lg text-sm font-bold disabled:opacity-40 dark:bg-amber-950/40 dark:text-amber-300" :disabled="!selectedIds.size || mutatingId !== null" @click="generateSelectedMissing">{{ t('backoffice.qrGenerator.generateMissing') }}</button>
        <button class="px-4 py-2 bg-blue-700 text-white rounded-lg font-bold text-sm disabled:opacity-40" :disabled="!selectedIds.size" @click="printSelected">🖨️ {{ t('backoffice.qrGenerator.printCount', { count: selectedIds.size }) }}</button>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-16"><div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" /></div>
    <div v-else-if="!tables.length" class="text-center py-20 text-gray-500 dark:text-gray-400">
      <div class="text-5xl mb-4">📱</div><p class="font-medium">{{ t('backoffice.qrGenerator.noTables') }}</p>
    </div>
    <div v-else class="space-y-8">
      <section v-for="[section, sectionTables] in grouped" :key="section">
        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wide mb-4 dark:text-gray-400">{{ section }}</h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          <article v-for="table in sectionTables" :id="`table-card-${table.id}`" :key="table.id" :class="['relative bg-white dark:bg-surface rounded-2xl border-2 p-4 flex flex-col items-center gap-3 transition-all', selectedIds.has(table.id) ? 'border-blue-600 bg-blue-50 shadow-md dark:border-blue-500 dark:bg-blue-950/40' : 'border-stone-200 dark:border-border']">
            <button class="absolute top-2 end-2 w-6 h-6 rounded-full border-2 text-xs" :class="selectedIds.has(table.id) ? 'bg-blue-600 border-blue-600 text-white' : 'border-stone-300 dark:border-gray-600'" @click="toggleSelect(table.id)">{{ selectedIds.has(table.id) ? '✓' : '' }}</button>
            <div class="w-28 h-28 bg-stone-50 dark:bg-white rounded-xl flex items-center justify-center overflow-hidden">
              <canvas v-if="tokenByTable.has(table.id)" :ref="el => { canvasRefs[table.id] = el as HTMLCanvasElement | null; if (el) renderTableQr(table.id) }" class="w-28 h-28" />
              <span v-else class="text-xs text-gray-400 text-center px-2">{{ t('backoffice.qrGenerator.notGenerated') }}</span>
            </div>
            <div class="text-center"><div class="font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.qrGenerator.tableNumber', { number: table.table_number }) }}</div><div v-if="table.section" class="text-xs text-gray-500 dark:text-gray-400">{{ table.section }}</div></div>
            <div class="w-full flex gap-1">
              <button v-if="!tokenByTable.has(table.id)" class="flex-1 py-1.5 bg-blue-700 text-white text-xs font-bold rounded-lg disabled:opacity-50" :disabled="mutatingId !== null" @click="mintOrRotate(table)">{{ t('backoffice.qrGenerator.generate') }}</button>
              <template v-else>
                <button class="flex-1 py-1.5 bg-stone-100 text-gray-700 text-xs font-semibold rounded-lg dark:bg-gray-700 dark:text-gray-200" @click="downloadQr(table)">⬇️ {{ t('backoffice.qrGenerator.download') }}</button>
                <button class="px-2 py-1.5 bg-red-50 text-red-700 text-xs font-semibold rounded-lg disabled:opacity-50 dark:bg-red-950/40 dark:text-red-300" :disabled="mutatingId !== null" @click="mintOrRotate(table, true)">{{ t('backoffice.qrGenerator.rotate') }}</button>
              </template>
            </div>
          </article>
        </div>
      </section>
    </div>

    <div class="mt-8 bg-blue-50 border border-blue-200 rounded-2xl p-4 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
      <p class="font-bold mb-1">💡 {{ t('backoffice.qrGenerator.howToUse') }}</p>
      <p class="text-xs">{{ t('backoffice.qrGenerator.securityNote') }}</p>
    </div>
  </div>
</template>
