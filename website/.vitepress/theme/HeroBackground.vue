<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"

// Pure CSS and SVG. The animation pauses when the hero is scrolled out of view; the page-wide
// pause for a hidden tab is in index.ts. Reduced motion shows the same picture, still.
const root = ref<HTMLElement | null>(null)
const off = ref(false)
let io: IntersectionObserver | undefined
onMounted(() => {
  if (!("IntersectionObserver" in window) || !root.value) return
  io = new IntersectionObserver(([e]) => (off.value = !e.isIntersecting))
  io.observe(root.value)
})
onBeforeUnmount(() => io?.disconnect())
</script>

<template>
  <div ref="root" :class="['hero-bg', { 'is-off': off }]" aria-hidden="true">
    <div class="blob b1" />
    <div class="blob b2" />
    <div class="blob b3" />
    <div class="grid" />
    <svg class="trace" viewBox="0 0 1440 640" preserveAspectRatio="xMidYMid slice" focusable="false">
      <path class="t t1" d="M0 470 H220 L250 470 L268 430 L292 520 L312 470 H560 L590 470 L606 444 L626 498 L644 470 H900 L930 470 L946 410 L972 540 L996 470 H1440" />
      <path class="t t2" d="M0 520 H380 L410 520 L424 498 L442 540 L458 520 H820 L850 520 L866 492 L888 548 L906 520 H1440" />
      <path class="t t3" d="M0 420 H300 L330 420 L346 396 L366 444 L382 420 H1100 L1130 420 L1148 380 L1170 460 L1190 420 H1440" />
    </svg>
    <div class="fade" />
  </div>
</template>
