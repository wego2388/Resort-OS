<script setup lang="ts">
// Public marketing landing page for Blue Bay El Kheima
</script>

<template>
  <div dir="rtl" class="min-h-screen bg-white">
    <!-- Hero -->
    <div class="relative bg-gradient-to-br from-blue-900 via-blue-800 to-blue-700 text-white overflow-hidden">
      <div class="absolute inset-0 opacity-10">
        <div class="absolute top-10 right-10 w-64 h-64 bg-white rounded-full blur-3xl"/>
        <div class="absolute bottom-0 left-0 w-96 h-96 bg-amber-400 rounded-full blur-3xl"/>
      </div>
      <div class="relative max-w-3xl mx-auto text-center px-6 py-20">
        <div class="text-5xl mb-4">🌊</div>
        <h1 class="text-4xl md:text-6xl font-black mb-4 leading-tight">Blue Bay El Kheima</h1>
        <p class="text-blue-200 text-lg md:text-xl mb-3">منتجع شاطئي فاخر على ساحل البحر الأحمر</p>
        <p class="text-blue-300 text-sm mb-10">شرم الشيخ • مصر</p>
        <RouterLink to="/book"
          class="inline-block bg-amber-400 text-blue-900 px-10 py-4 rounded-2xl font-black text-lg hover:bg-amber-300 transition-all hover:shadow-xl hover:-translate-y-0.5">
          احجز الآن
        </RouterLink>
      </div>
    </div>

    <!-- Features -->
    <div class="max-w-4xl mx-auto px-6 py-16">
      <h2 class="text-3xl font-black text-gray-900 text-center mb-10">ما يميزنا</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div v-for="feat in features" :key="feat.title"
          class="text-center p-6 bg-stone-50 rounded-2xl border border-stone-200">
          <div class="text-4xl mb-3">{{ feat.icon }}</div>
          <h3 class="font-bold text-gray-900 text-lg mb-2">{{ feat.title }}</h3>
          <p class="text-gray-500 text-sm leading-relaxed">{{ feat.desc }}</p>
        </div>
      </div>
    </div>

    <!-- CTA -->
    <div class="bg-blue-700 py-16 text-center px-6">
      <h2 class="text-3xl font-black text-white mb-4">ابدأ تجربتك معنا اليوم</h2>
      <p class="text-blue-200 mb-8 text-lg">أسعار تنافسية وخدمة لا مثيل لها</p>
      <RouterLink to="/book"
        class="inline-block bg-white text-blue-700 px-10 py-4 rounded-2xl font-black text-lg hover:bg-blue-50 transition-colors">
        استفسر عن الحجز
      </RouterLink>
    </div>
  </div>
</template>

<script lang="ts">
const features = [
  { icon: '🏖️', title: 'شاطئ خاص', desc: 'استمتع بشاطئ خاص على البحر الأحمر مع مناظر خلابة لا تُضاهى' },
  { icon: '🍽️', title: 'مطبخ عالمي', desc: 'أشهى الأطباق العالمية والمحلية تُعدّ لك بأيدي طهاة محترفين' },
  { icon: '🌟', title: 'خدمة 5 نجوم', desc: 'فريق متخصص يعمل على مدار الساعة لضمان تجربة لا تُنسى' },
]
</script>
