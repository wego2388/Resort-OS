<template>
  <div class="flex flex-col gap-4 p-4">
    <div v-for="i in 4" :key="i" class="owner-card">
      <div class="skeleton h-3 w-1/3 mb-4 rounded" />
      <div class="skeleton h-9 w-2/3 mb-3 rounded" />
      <div class="skeleton h-10 w-full mb-2 rounded" />
      <div class="skeleton h-3 w-1/4 rounded" />
    </div>
  </div>
</template>
