import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    proxy: {
      // VITE_API_PROXY_TARGET لو محتاج تشغّل نسخة باك إند تانية على بورت
      // مختلف (بيئة اختبار منفصلة عن السيرفر الرئيسي) — نفس الإعداد
      // المستخدم فعليًا في apps/el-kheima/vite.config.ts، بدون ما يلمس
      // القيمة الافتراضية لباقي المطورين/الجلسات.
      '/api': { target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8005', changeOrigin: true },
      '/ws':  { target: (process.env.VITE_API_PROXY_TARGET || 'http://localhost:8005').replace('http', 'ws'), ws: true },
    },
  },
})
