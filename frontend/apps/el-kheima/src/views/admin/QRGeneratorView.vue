<script setup lang="ts">
/**
 * QRGeneratorView — توليد وطباعة QR codes لطاولات منافذ الدايننج.
 * يستخدم qrcode.js عبر CDN أو الـ Canvas API المدمج في المتصفح.
 * المدير يختار المنفذ، يختار الطاولة، يطبع أو يحمّل الـ QR.
 *
 * DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): كانت restaurant/cafe تابين
 * ثابتين (موديولين منفصلين، endpoints مختلفة) — دلوقتي قايمة منافذ ديناميكية
 * حقيقية من /dining/outlets (بتغطي أي outlet_type مستقبلي من غير تعديل هنا).
 * الـ QR بيشاور على `/order/{outlet_id}/{table_id}` بدل `/order/{restaurant|
 * cafe}/{table_id}` القديم — ⚠️ يعني أي QR مطبوع قبل الـ cutover بقى غير
 * صالح، لازم إعادة طباعة كل QR الطاولات من هنا من جديد.
 */
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { api, ENDPOINTS , useAuthStore } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const toast    = useToast()
const route    = useRoute()
const auth = useAuthStore()
const branchId = auth.branchId

// ── استخرج base URL من location الحالي عشان QR يشاور على العنوان الصحيح ──
const PUBLIC_BASE = computed(() => {
  // الـ QR بيشير للـ public app (apps/public) — بنفترض إنها على نفس الـ host
  // في port 5174 في dev، أو /order/* في production (كأقل تقدير نستخدم
  // window.location.origin + المسار المعروف).
  const origin = window.location.origin.replace(':5173', ':5174').replace(':5175', ':5174')
  return origin
})

interface Outlet { id: number; name: string; name_ar: string | null; outlet_type: string; is_active: boolean }
interface Table { id: number; table_number: string; section: string | null; status: string }

const outlets        = ref<Outlet[]>([])
const activeOutletId = ref<number | null>(null)
const tables          = ref<Table[]>([])
const loading         = ref(false)
const selectedIds     = ref<Set<number>>(new Set())
const canvasRefs      = ref<Record<number, HTMLCanvasElement | null>>({})

function outletLabel(o: Outlet): string {
  return o.name_ar || o.name
}
const activeOutletLabel = computed(() => {
  const o = outlets.value.find(o => o.id === activeOutletId.value)
  return o ? outletLabel(o) : ''
})

// دعم query params من شاشات إدارة الطاولات: ?outlet=12&highlight=5
// يختار المنفذ الصح ويحدد الطاولة المطلوبة تلقائياً
onMounted(async () => {
  try {
    const { data } = await api.get(ENDPOINTS.dining.outlets, { params: { branch_id: branchId, active_only: true } })
    outlets.value = data?.items ?? data ?? []
  } catch {
    toast.error('تعذّر تحميل منافذ الدايننج')
    return
  }
  const queryOutlet = route.query.outlet ? parseInt(route.query.outlet as string) : NaN
  activeOutletId.value = !isNaN(queryOutlet) && outlets.value.some(o => o.id === queryOutlet)
    ? queryOutlet
    : (outlets.value[0]?.id ?? null)

  await loadTables()
  if (route.query.highlight) {
    const id = parseInt(route.query.highlight as string)
    if (!isNaN(id)) {
      selectedIds.value = new Set([id])
      await nextTick()
      document.getElementById(`table-card-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }
})

async function loadTables() {
  if (activeOutletId.value == null) { tables.value = []; return }
  loading.value = true
  tables.value = []
  selectedIds.value = new Set()
  try {
    const { data } = await api.get(ENDPOINTS.dining.tables(activeOutletId.value))
    tables.value = data.tables ?? data.items ?? data
  } catch {
    toast.error('تعذّر تحميل الطاولات')
  } finally {
    loading.value = false
  }
}

function toggleSelect(id: number) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selectedIds.value = s
}

function selectAll() {
  selectedIds.value = new Set(tables.value.map(t => t.id))
}
function clearAll() {
  selectedIds.value = new Set()
}

// ── QR generation — native Canvas fallback ────────────────────────────
// محاولة أولى: qrserver.com (أسرع، لا يحتاج lib). لو النت قاطع أو المتصفح
// حجب الـ request، الصورة بتـ fallback لـ Canvas محلي عبر qrcode-svg مضغوط
// (tiny-qr) محسوب في الـ browser مباشرة — بدون dependency خارجية إضافية.
// الـ fallback بيشتغل تلقائياً عبر @error على الـ <img>.

function orderPath(tableId: number): string {
  return `/order/${activeOutletId.value}/${tableId}`
}

function qrUrl(tableId: number): string {
  const target = encodeURIComponent(`${PUBLIC_BASE.value}${orderPath(tableId)}`)
  return `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${target}&margin=10`
}

/** Canvas fallback — يُرسم لو <img> فشل في التحميل (offline / مُحجوب).
 * يستخدم script lazy من CDN أو يرسم QR بسيط بـ ASCII matrix (placeholder). */
async function drawQrFallback(tableId: number, canvas: HTMLCanvasElement) {
  const url = `${PUBLIC_BASE.value}${orderPath(tableId)}`

  // نحاول نحمّل مكتبة qrcode خفيفة من CDN (تعمل offline لو كانت cached)
  try {
    // @ts-ignore — dynamic global script injection
    if (!window.QRCode) {
      await new Promise<void>((resolve, reject) => {
        const s = document.createElement('script')
        s.src = 'https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js'
        s.onload = () => resolve()
        s.onerror = () => reject(new Error('cdn failed'))
        document.head.appendChild(s)
      })
    }
    // @ts-ignore
    await window.QRCode.toCanvas(canvas, url, { width: 200, margin: 2 })
  } catch {
    // آخر fallback: نكتب الـ URL كنص مباشرة على الـ canvas
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    canvas.width = 200; canvas.height = 60
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, 200, 60)
    ctx.fillStyle = '#1e40af'
    ctx.font = 'bold 10px monospace'
    ctx.textAlign = 'center'
    ctx.fillText('⚠️ QR — اتصل بالإنترنت', 100, 20)
    ctx.font = '8px monospace'
    ctx.fillStyle = '#374151'
    const words = url.match(/.{1,28}/g) ?? []
    words.forEach((w, i) => ctx.fillText(w, 100, 34 + i * 12))
  }
}

function tableLabel(table: Table): string {
  return table.section ? `${table.section} — ${table.table_number}` : `طاولة ${table.table_number}`
}

// ── Print selected ────────────────────────────────────────────────────
function printSelected() {
  const selectedTables = tables.value.filter(t => selectedIds.value.has(t.id))
  if (selectedTables.length === 0) { toast.error('اختر طاولة واحدة على الأقل'); return }

  const outlet_ar = activeOutletLabel.value

  const html = `<!DOCTYPE html>
<html dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>QR Codes — ${outlet_ar}</title>
  <style>
    body { font-family: 'Cairo', sans-serif; margin: 0; padding: 20px; background: #fff; }
    .grid { display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }
    .card {
      border: 2px solid #d4a017; border-radius: 16px; padding: 20px;
      text-align: center; width: 220px; page-break-inside: avoid;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .card img { width: 180px; height: 180px; }
    .table-name { font-size: 20px; font-weight: 900; margin-top: 10px; color: #1a1a1a; }
    .module-name { font-size: 13px; color: #888; margin-top: 4px; }
    .url { font-size: 9px; color: #aaa; margin-top: 6px; word-break: break-all; }
    @media print {
      body { padding: 10px; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <div style="text-align:center; margin-bottom:20px; font-size:14px; color:#666;" class="no-print">
    اضغط Ctrl+P للطباعة
  </div>
  <div class="grid">
    ${selectedTables.map(t => {
      const fullUrl = `${PUBLIC_BASE.value}${orderPath(t.id)}`
      const qr = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(fullUrl)}&margin=10`
      return `<div class="card">
        <img src="${qr}" alt="QR ${t.table_number}"
          onerror="this.style.display='none';var c=this.nextElementSibling;c.style.display='block';if(window.QRCode){QRCode.toCanvas(c,'${fullUrl}',{width:180,margin:2})}else{var s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js';s.onload=function(){QRCode.toCanvas(c,'${fullUrl}',{width:180,margin:2})};document.head.appendChild(s)}" />
        <canvas style="display:none;width:180px;height:180px"></canvas>
        <div class="table-name">طاولة ${t.table_number}</div>
        <div class="module-name">${outlet_ar}</div>
        <div class="url">${fullUrl}</div>
      </div>`
    }).join('\n')}
  </div>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) { toast.error('المتصفح منع فتح نافذة الطباعة — فعّل النوافذ المنبثقة'); return }
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 800)
}

// ── Download single QR ────────────────────────────────────────────────
// #22: بدل fetch من qrserver.com (بيفشل offline أو لو الـ API اتغيّر)،
// بنستخدم canvas محلي — نفس منطق drawQrFallback لكن بـ offscreen canvas
// عشان مايأثرش على العرض، وبنصدّر PNG محليًا من toDataURL.
async function downloadQr(table: Table) {
  const targetUrl = `${PUBLIC_BASE.value}${orderPath(table.id)}`

  // خطوة 1: حاول تحميل QRCode lib من CDN (cached بعد أول مرة)
  try {
    if (!window.QRCode) {
      await new Promise<void>((resolve, reject) => {
        const s = document.createElement('script')
        s.src = 'https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js'
        s.onload = () => resolve()
        s.onerror = () => reject(new Error('cdn failed'))
        document.head.appendChild(s)
      })
    }
    // offscreen canvas — مش بيظهر للمستخدم
    const offscreen = document.createElement('canvas')
    // @ts-ignore
    await window.QRCode.toCanvas(offscreen, targetUrl, { width: 400, margin: 2 })
    const dataUrl = offscreen.toDataURL('image/png')
    const a = document.createElement('a')
    a.href     = dataUrl
    a.download = `qr-${activeOutletId.value}-${table.table_number}.png`
    a.click()
    return
  } catch {
    // CDN فشل — fallback لـ qrserver.com
  }

  // خطوة 2: fallback لـ qrserver.com (يشتغل لو في نت بس CDN اتحجب)
  try {
    const apiUrl = qrUrl(table.id)
    const res    = await fetch(apiUrl)
    if (!res.ok) throw new Error('api failed')
    const blob = await res.blob()
    const a    = document.createElement('a')
    a.href     = URL.createObjectURL(blob)
    a.download = `qr-${activeOutletId.value}-${table.table_number}.png`
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 5000)
  } catch {
    toast.error('تعذّر تنزيل الـ QR — تأكد من الاتصال بالإنترنت')
  }
}

const grouped = computed(() => {
  const map = new Map<string, Table[]>()
  for (const t of tables.value) {
    const key = t.section || 'عام'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(t)
  }
  return Array.from(map.entries())
})
</script>

<template>
  <div dir="rtl" class="p-6 max-w-6xl mx-auto">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-black text-gray-900 dark:text-gray-100">📱 توليد QR Codes</h1>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">اختر الطاولات وطبع QR codes جاهزة للتعليق</p>
      </div>
      <div class="flex gap-2">
        <button
          @click="selectAll"
          class="px-3 py-2 bg-stone-100 dark:bg-gray-700 hover:bg-stone-200 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-semibold transition-colors"
        >تحديد الكل</button>
        <button
          @click="clearAll"
          class="px-3 py-2 bg-stone-100 dark:bg-gray-700 hover:bg-stone-200 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-semibold transition-colors"
        >إلغاء التحديد</button>
        <button
          @click="printSelected"
          :disabled="selectedIds.size === 0"
          class="px-4 py-2 bg-blue-700 text-white rounded-lg font-bold text-sm hover:bg-blue-800 transition-colors disabled:opacity-40"
        >🖨️ طباعة ({{ selectedIds.size }})</button>
      </div>
    </div>

    <!-- Outlet tabs — ديناميكية من /dining/outlets (أي عدد منافذ، مش بس اتنين) -->
    <div v-if="outlets.length" class="flex gap-2 mb-6 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl w-fit flex-wrap">
      <button
        v-for="o in outlets"
        :key="o.id"
        @click="activeOutletId = o.id; loadTables()"
        :class="[
          'px-5 py-2 rounded-lg text-sm font-bold transition-all',
          activeOutletId === o.id ? 'bg-white dark:bg-surface text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700',
        ]"
      >{{ outletLabel(o) }}</button>
    </div>
    <div v-else-if="!loading" class="text-sm text-gray-400 dark:text-gray-500 mb-6">لا توجد منافذ دايننج مفعّلة</div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <!-- Empty -->
    <div v-else-if="tables.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
      <div class="text-5xl mb-4">📱</div>
      <p class="font-medium text-gray-600 dark:text-gray-500">لا توجد طاولات مضافة</p>
      <p class="text-sm mt-1">اذهب لإدارة الطاولات وأضف طاولات أولاً</p>
    </div>

    <!-- Tables grid grouped by section -->
    <div v-else class="space-y-8">
      <div v-for="[section, sectionTables] in grouped" :key="section">
        <h2 class="text-sm font-bold text-gray-500 dark:text-gray-500 uppercase tracking-wide mb-4 flex items-center gap-2">
          <span class="flex-1 border-b border-stone-200 dark:border-border" />
          <span>{{ section }}</span>
          <span class="flex-1 border-b border-stone-200 dark:border-border" />
        </h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          <div
            v-for="table in sectionTables"
            :key="table.id"
            :id="`table-card-${table.id}`"
            @click="toggleSelect(table.id)"
            :class="[
              'relative bg-white dark:bg-surface rounded-2xl border-2 p-4 flex flex-col items-center gap-3 cursor-pointer transition-all hover:shadow-md',
              selectedIds.has(table.id) ? 'border-blue-600 shadow-md bg-blue-50' : 'border-stone-200 dark:border-border',
            ]"
          >
            <!-- Checkmark -->
            <div
              :class="[
                'absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all',
                selectedIds.has(table.id) ? 'bg-blue-600 border-blue-600' : 'border-stone-300',
              ]"
            >
              <span v-if="selectedIds.has(table.id)" class="text-white text-xs font-black">✓</span>
            </div>

            <!-- QR Image — fallback to canvas if external API unreachable -->
            <div class="w-24 h-24 rounded-lg overflow-hidden flex items-center justify-center bg-stone-50 dark:bg-gray-800/60">
              <img
                :src="qrUrl(table.id)"
                :alt="`QR طاولة ${table.table_number}`"
                class="w-24 h-24 rounded-lg"
                loading="lazy"
                @error="(e) => { (e.target as HTMLImageElement).style.display='none'; const c = canvasRefs[table.id]; if(c) drawQrFallback(table.id, c) }"
              />
              <canvas
                :ref="(el) => { canvasRefs[table.id] = el as HTMLCanvasElement | null }"
                class="w-24 h-24 rounded-lg hidden"
                style="display:none"
              />
            </div>

            <!-- Label -->
            <div class="text-center">
              <div class="font-black text-gray-900 dark:text-gray-100">طاولة {{ table.table_number }}</div>
              <div v-if="table.section" class="text-xs text-gray-500 dark:text-gray-500">{{ table.section }}</div>
            </div>

            <!-- Download btn -->
            <button
              @click.stop="downloadQr(table)"
              class="w-full py-1.5 bg-stone-100 dark:bg-gray-700 hover:bg-stone-200 text-gray-600 dark:text-gray-500 text-xs font-semibold rounded-lg transition-colors"
            >⬇️ تحميل</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Info box -->
    <div class="mt-8 bg-blue-50 border border-blue-200 rounded-2xl p-4 text-sm text-blue-800">
      <p class="font-bold mb-1">💡 كيفية الاستخدام:</p>
      <ul class="space-y-1 text-xs list-disc list-inside text-blue-700">
        <li>اختر الطاولات بالضغط عليها</li>
        <li>اضغط "طباعة" لفتح نافذة الطباعة مع كل QR codes المختارة</li>
        <li>أو اضغط "تحميل" على أي طاولة لتحميل الـ QR منفرداً</li>
        <li>الـ QR بيشاور على شاشة الضيف (/order/{{ activeOutletId }}/[table_id])</li>
      </ul>
    </div>

  </div>
</template>
