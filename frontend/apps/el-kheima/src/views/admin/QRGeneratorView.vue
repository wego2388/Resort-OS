<script setup lang="ts">
/**
 * QRGeneratorView — توليد وطباعة QR codes لطاولات المطعم والكافيه
 * يستخدم qrcode.js عبر CDN أو الـ Canvas API المدمج في المتصفح.
 * المدير يختار الموديول، يختار الطاولة، يطبع أو يحمّل الـ QR.
 */
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@resort-os/core'
import { useToast } from '@resort-os/ui'

const toast    = useToast()
const route    = useRoute()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── استخرج base URL من location الحالي عشان QR يشاور على العنوان الصحيح ──
const PUBLIC_BASE = computed(() => {
  // الـ QR بيشير للـ public app (apps/public) — بنفترض إنها على نفس الـ host
  // في port 5174 في dev، أو /order/* في production (كأقل تقدير نستخدم
  // window.location.origin + المسار المعروف).
  const origin = window.location.origin.replace(':5173', ':5174').replace(':5175', ':5174')
  return origin
})

interface Table { id: number; table_number: string; section: string | null; status: string }

const activeModule = ref<'restaurant' | 'cafe'>('restaurant')
const tables       = ref<Table[]>([])
const loading      = ref(false)
const selectedIds  = ref<Set<number>>(new Set())
const canvasRefs   = ref<Record<number, HTMLCanvasElement | null>>({})

// دعم query params من TablesAdminView: ?module=cafe&highlight=5
// يختار الموديول الصح ويحدد الطاولة المطلوبة تلقائياً
onMounted(async () => {
  if (route.query.module === 'cafe' || route.query.module === 'restaurant') {
    activeModule.value = route.query.module as 'restaurant' | 'cafe'
  }
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
  loading.value = true
  tables.value = []
  selectedIds.value = new Set()
  try {
    const { data } = await api.get(`/api/v1/${activeModule.value}/tables`, {
      params: { branch_id: branchId },
    })
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

function qrUrl(tableId: number): string {
  const path = activeModule.value === 'restaurant'
    ? `/order/restaurant/${tableId}`
    : `/order/cafe/${tableId}`
  const target = encodeURIComponent(`${PUBLIC_BASE.value}${path}`)
  return `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${target}&margin=10`
}

/** Canvas fallback — يُرسم لو <img> فشل في التحميل (offline / مُحجوب).
 * يستخدم script lazy من CDN أو يرسم QR بسيط بـ ASCII matrix (placeholder). */
async function drawQrFallback(tableId: number, canvas: HTMLCanvasElement) {
  const path = activeModule.value === 'restaurant'
    ? `/order/restaurant/${tableId}`
    : `/order/cafe/${tableId}`
  const url = `${PUBLIC_BASE.value}${path}`

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

  const module_ar = activeModule.value === 'restaurant' ? 'المطعم' : 'الكافيه'

  const html = `<!DOCTYPE html>
<html dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>QR Codes — ${module_ar}</title>
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
      const path = activeModule.value === 'restaurant'
        ? `/order/restaurant/${t.id}`
        : `/order/cafe/${t.id}`
      const fullUrl = `${PUBLIC_BASE.value}${path}`
      const qr = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(fullUrl)}&margin=10`
      return `<div class="card">
        <img src="${qr}" alt="QR ${t.table_number}"
          onerror="this.style.display='none';var c=this.nextElementSibling;c.style.display='block';if(window.QRCode){QRCode.toCanvas(c,'${fullUrl}',{width:180,margin:2})}else{var s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js';s.onload=function(){QRCode.toCanvas(c,'${fullUrl}',{width:180,margin:2})};document.head.appendChild(s)}" />
        <canvas style="display:none;width:180px;height:180px"></canvas>
        <div class="table-name">طاولة ${t.table_number}</div>
        <div class="module-name">${module_ar}</div>
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
  const path = activeModule.value === 'restaurant'
    ? `/order/restaurant/${table.id}`
    : `/order/cafe/${table.id}`
  const targetUrl = `${PUBLIC_BASE.value}${path}`

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
    a.download = `qr-${activeModule.value}-${table.table_number}.png`
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
    a.download = `qr-${activeModule.value}-${table.table_number}.png`
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
        <h1 class="text-xl font-black text-gray-900">📱 توليد QR Codes</h1>
        <p class="text-xs text-gray-400 mt-1">اختر الطاولات وطبع QR codes جاهزة للتعليق</p>
      </div>
      <div class="flex gap-2">
        <button
          @click="selectAll"
          class="px-3 py-2 bg-stone-100 hover:bg-stone-200 text-gray-700 rounded-lg text-sm font-semibold transition-colors"
        >تحديد الكل</button>
        <button
          @click="clearAll"
          class="px-3 py-2 bg-stone-100 hover:bg-stone-200 text-gray-700 rounded-lg text-sm font-semibold transition-colors"
        >إلغاء التحديد</button>
        <button
          @click="printSelected"
          :disabled="selectedIds.size === 0"
          class="px-4 py-2 bg-blue-700 text-white rounded-lg font-bold text-sm hover:bg-blue-800 transition-colors disabled:opacity-40"
        >🖨️ طباعة ({{ selectedIds.size }})</button>
      </div>
    </div>

    <!-- Module tabs -->
    <div class="flex gap-2 mb-6 bg-stone-100 p-1 rounded-xl w-fit">
      <button
        v-for="m in [{ val: 'restaurant', label: '🍽️ المطعم' }, { val: 'cafe', label: '☕ الكافيه' }]"
        :key="m.val"
        @click="activeModule = (m.val as 'restaurant' | 'cafe'); loadTables()"
        :class="[
          'px-5 py-2 rounded-lg text-sm font-bold transition-all',
          activeModule === m.val ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700',
        ]"
      >{{ m.label }}</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-16">
      <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
    </div>

    <!-- Empty -->
    <div v-else-if="tables.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-400">
      <div class="text-5xl mb-4">📱</div>
      <p class="font-medium text-gray-600">لا توجد طاولات مضافة</p>
      <p class="text-sm mt-1">اذهب لإدارة الطاولات وأضف طاولات أولاً</p>
    </div>

    <!-- Tables grid grouped by section -->
    <div v-else class="space-y-8">
      <div v-for="[section, sectionTables] in grouped" :key="section">
        <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wide mb-4 flex items-center gap-2">
          <span class="flex-1 border-b border-stone-200" />
          <span>{{ section }}</span>
          <span class="flex-1 border-b border-stone-200" />
        </h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          <div
            v-for="table in sectionTables"
            :key="table.id"
            :id="`table-card-${table.id}`"
            @click="toggleSelect(table.id)"
            :class="[
              'relative bg-white rounded-2xl border-2 p-4 flex flex-col items-center gap-3 cursor-pointer transition-all hover:shadow-md',
              selectedIds.has(table.id) ? 'border-blue-600 shadow-md bg-blue-50' : 'border-stone-200',
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
            <div class="w-24 h-24 rounded-lg overflow-hidden flex items-center justify-center bg-stone-50">
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
              <div class="font-black text-gray-900">طاولة {{ table.table_number }}</div>
              <div v-if="table.section" class="text-xs text-gray-500">{{ table.section }}</div>
            </div>

            <!-- Download btn -->
            <button
              @click.stop="downloadQr(table)"
              class="w-full py-1.5 bg-stone-100 hover:bg-stone-200 text-gray-600 text-xs font-semibold rounded-lg transition-colors"
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
        <li>الـ QR بيشاور على شاشة الضيف ({{ activeModule === 'restaurant' ? '/order/restaurant' : '/order/cafe' }}/[id])</li>
      </ul>
    </div>

  </div>
</template>
