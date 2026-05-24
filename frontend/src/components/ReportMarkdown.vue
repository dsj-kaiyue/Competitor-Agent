<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

const props = defineProps<{ markdown: string }>()
const md = new MarkdownIt({ html: false, linkify: true })
const html = computed(() => md.render(props.markdown))
</script>

<template>
  <article class="markdown-body" v-html="html" />
</template>

<style scoped>
.markdown-body {
  line-height: 1.75;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 20px 0 10px;
}

.markdown-body :deep(li) {
  margin: 6px 0;
}
</style>
