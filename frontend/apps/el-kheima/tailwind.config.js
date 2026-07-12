import dsPreset from '../../packages/ui/tailwind-preset.js'

/** @type {import('tailwindcss').Config} */
export default {
  // ⚠️ باج حقيقي اتكشف أثناء اختبار حي لشاشة التايم شير: content مكنش شامل
  // '../../packages/ui/src' (@resort-os/ui — مصدر مباشر، مفيش build step،
  // مكوّناته بتتحمّل زي أي كود تاني في المشروع). يعني أي Tailwind class
  // مستخدمة بس جوه مكوّنات الباكدج المشتركة (ToastContainer، ConfirmDialogContainer)
  // ومش مستخدمة حرفيًا في أي مكان تاني في el-kheima نفسه — كانت بتتشال تمامًا من
  // الـ CSS النهائي بصمت (JIT scanner عمره ما شافها). النتيجة الفعلية: تنبيهات
  // toast.error() (نفس النظام اللي اتستخدم في مراجعة UI/UX النهاردة لعرض رسائل
  // خطأ حقيقية بدل البلع الصامت) كانت بتظهر في أسفل الصفحة من غير أي تمركز أو
  // z-index صحيح (fixed/top-4/left-1/2/-translate-x-1/2/z-[100] كلهم مفقودين
  // من الـ CSS) — يعني الموظف ممكن يفوّت رسالة خطأ حقيقية ليها معنى (زي رفض
  // دفعة زيادة عن المستحق) لأنها بتظهر في مكان غير متوقع بدون أي تنسيق.
  content: ['./index.html', './src/**/*.{vue,ts}', '../../packages/ui/src/**/*.{vue,ts}'],
  // Shared Design System preset (packages/ui/tailwind-preset.js) — semantic
  // color tokens, type scale, elevation, motion, responsive tokens. `extend`
  // below still merges on top of it (Tailwind presets deep-merge), so
  // el-kheima's own primary/gold/resort palette and Cairo font are untouched.
  presets: [dsPreset],
  darkMode: 'class',
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
