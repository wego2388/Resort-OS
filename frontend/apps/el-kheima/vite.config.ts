import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import { resolve } from 'path'

function validateProductionPublicSiteUrl(value: string | undefined): string {
  if (!value?.trim()) {
    throw new Error('VITE_PUBLIC_SITE_URL is required for a production build')
  }

  const parsed = new URL(value)
  if (parsed.protocol !== 'https:') {
    throw new Error('VITE_PUBLIC_SITE_URL must use https for a production build')
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('VITE_PUBLIC_SITE_URL must not contain credentials, a query, or a fragment')
  }
  return parsed.toString().replace(/\/+$/, '')
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  if (mode === 'production') {
    validateProductionPublicSiteUrl(env.VITE_PUBLIC_SITE_URL)
  }

  return {
    plugins: [
      vue(),
      // ⚠️ vue-i18n's default runtime compiles message JSON into executable
      // functions via `new Function()` — production's CSP is `script-src
      // 'self'` with no `unsafe-eval` (correctly; weakening the CSP instead
      // would be the wrong fix), so the entire app failed to mount at all on
      // first load: "EvalError: ... violates ... script-src 'self'". This
      // plugin precompiles every message catalog to plain JS at build time,
      // so no runtime eval is ever needed. `include` covers @resort-os/core's
      // shared locale JSON (imported directly in packages/core/src/i18n/*.ts)
      // since that's the actual source of the messages this app ships.
      VueI18nPlugin({
        include: resolve(__dirname, '../../packages/core/src/i18n/locales/**'),
      }),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['icon-192.png', 'icon-512.png'],
        manifest: {
          name: 'Resort OS — El Kheima',
          short_name: 'Resort OS',
          description: 'نظام إدارة المنتجع المتكامل — نقطة البيع، المطبخ، العمليات، الإدارة، الجرسون، بوابة الموظفين',
          theme_color: '#0B4F8A',
          background_color: '#F9F7F4',
          display: 'standalone',
          start_url: '/',
          scope: '/',
          dir: 'rtl',
          lang: 'ar-EG',
          icons: [
            { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          ],
        },
        workbox: {
          // Authenticated API responses must never outlive the current operator,
          // branch, or shift. Only the generated static application shell is
          // precached; offline writes use the separately identity-scoped IDB
          // queue and are reconciled with the server when the same user returns.
          cleanupOutdatedCaches: true,
          runtimeCaching: [],
        },
      }),
    ],
    // VueI18nPlugin precompiles every message to an AST object (`{t:0,b:{...}}`
    // — verified by inspecting the built bundle), not a `new Function()`-based
    // compiled function. That AST still has to be evaluated into a plain
    // string at translate() time, and vue-i18n only does that evaluation when
    // its message compiler is registered — which happens exactly when
    // `__INTLIFY_JIT_COMPILATION__` is true. Setting it false (a previous,
    // wrong attempt at this fix) skips compiler registration entirely, so
    // translate() gets the raw AST object back instead of a string and throws
    // `SyntaxError: Unexpected return type in composer` on every single
    // `t()` call, everywhere, on first render — confirmed via a real headless
    // browser run + source-mapped stack trace, not just a static bundle grep.
    // With it true, the registered compiler evaluates our precompiled AST
    // directly (no parsing, no codegen, no `new Function`) — verified `grep -c
    // "new Function"` still comes back 0 across every chunk with this set.
    define: {
      __INTLIFY_JIT_COMPILATION__: true,
      __INTLIFY_PROD_DEVTOOLS__: false,
    },
    resolve: {
      alias: { '@': resolve(__dirname, 'src') },
    },
    server: {
      host: true,
      proxy: {
        // ws: true هنا مهم — الـ WebSocket الحقيقي (KDS) مسجّل تحت نفس مسار
        // /api/v1/... زي أي endpoint تاني، مش تحت /ws منفصل. الإعداد القديم
        // (/ws بروكسي لمسار مختلف تمامًا عن مسار الـ backend الحقيقي) كان
        // معناه إن أي اتصال WebSocket من الفرونت إند مستحيل يوصل للباك إند خالص.
        // VITE_API_PROXY_TARGET لو محتاج تشغّل نسخة باك إند تانية على بورت
        // مختلف (بيئة اختبار منفصلة عن السيرفر الرئيسي، بدون ما تلمس القيمة
        // الافتراضية اللي باقي المطورين/الجلسات معتمدين عليها).
        '/api': {
          target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8005',
          changeOrigin: true,
          ws: true,
        },
      },
    },
  }
})
