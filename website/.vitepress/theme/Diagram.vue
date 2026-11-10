<script setup lang="ts">
import { computed } from "vue"
import { layout } from "./diagrams/layout"
import { specs } from "./diagrams/specs"

const props = defineProps<{ name: string; caption?: string }>()
const spec = computed(() => specs[props.name])
const variants = computed(() => [
  { key: "wide", cls: "dg-wide", l: layout(spec.value, true) },
  { key: "narrow", cls: "dg-narrow", l: layout(spec.value, false) },
])
</script>

<template>
  <figure class="dg" v-if="spec">
    <svg
      v-for="v in variants"
      :key="v.key"
      :class="['dg-svg', v.cls]"
      :viewBox="`0 0 ${v.l.width} ${v.l.height}`"
      role="img"
      :aria-label="spec.alt"
      focusable="false"
    >
      <title>{{ spec.alt }}</title>
      <defs>
        <marker :id="`dg-${name}-${v.key}`" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M1 1 9 5 1 9z" class="dg-head" />
        </marker>
      </defs>
      <g aria-hidden="true">
        <g v-for="(e, i) in v.l.edges" :key="i">
          <path :d="e.d" class="dg-edge" />
          <path
            :d="e.d"
            class="dg-flow"
            :marker-end="`url(#dg-${name}-${v.key})`"
            :marker-start="e.both ? `url(#dg-${name}-${v.key})` : undefined"
          />
          <g v-if="e.label">
            <rect :x="e.lx - e.label.length * 3.6 - 6" :y="e.ly - 10" :width="e.label.length * 7.2 + 12" height="20" rx="10" class="dg-pill" />
            <text :x="e.lx" :y="e.ly + 4" text-anchor="middle" class="dg-elabel">{{ e.label }}</text>
          </g>
        </g>
        <g v-for="n in v.l.nodes" :key="n.id" :class="['dg-node', `k-${n.kind ?? 'plain'}`]">
          <rect :x="n.x" :y="n.y" :width="n.w" :height="n.h" rx="10" />
          <text
            v-for="(t, i) in n.lines"
            :key="'l' + i"
            :x="n.x + n.w / 2"
            :y="n.y + 24 + i * 18"
            text-anchor="middle"
            class="dg-label"
          >{{ t }}</text>
          <text
            v-for="(t, i) in n.subLines"
            :key="'s' + i"
            :x="n.x + n.w / 2"
            :y="n.y + 24 + n.lines.length * 18 + 2 + i * 15"
            text-anchor="middle"
            class="dg-sub"
          >{{ t }}</text>
        </g>
      </g>
    </svg>
    <figcaption v-if="caption">{{ caption }}</figcaption>
  </figure>
</template>
