/** @type {import('tailwindcss').Config} */
export default {
  // ⚠️ نفس باج el-kheima's tailwind.config.js — content مكنش شامل
  // '../../packages/ui/src'، يعني Tailwind classes مستخدمة بس جوه مكوّنات
  // @resort-os/ui المشتركة (ToastContainer مثلاً) كانت بتتشال بصمت من الـ CSS.
  content: ['./index.html', './src/**/*.{vue,ts}', '../../packages/ui/src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0B4F8A',
          50: '#EFF6FF', 100: '#DBEAFE', 200: '#BFDBFE',
          300: '#93C5FD', 400: '#60A5FA', 500: '#3B82F6',
          600: '#2563EB', 700: '#0B4F8A', 800: '#083C6A', 900: '#05294A',
        },
        gold: {
          DEFAULT: '#C9963C',
          light: '#F5D78E', dark: '#A07530',
        },
        resort: {
          bg: '#F9F7F4',
          surface: '#FFFFFF',
          border: '#E5E0D8',
        },
      },
      fontFamily: {
        sans: ['Cairo', 'Tajawal', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
