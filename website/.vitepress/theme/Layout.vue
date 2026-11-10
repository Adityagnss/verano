<script setup lang="ts">
import DefaultTheme from "vitepress/theme"
import HeroBackground from "./HeroBackground.vue"
import HeroReadout from "./HeroReadout.vue"

const { Layout } = DefaultTheme
</script>

<template>
  <Layout>
    <template #home-hero-before><HeroBackground /></template>
    <template #home-hero-image><HeroReadout /></template>
  </Layout>
</template>
