<!-- 快速模板标签 -->
<template>
  <div class="quick-templates">
    <a-tag
      v-for="tpl in templates"
      :key="tpl.label" :color="tpl.color"
      @click="$emit('select', tpl.text)"
      class="quick-tag"
    >{{ tpl.label }}</a-tag>
  </div>
</template>

<script setup>
import { QUICK_TEMPLATES } from '../../constants';
defineEmits(['select']);
const templates = QUICK_TEMPLATES;
</script>

<style lang="scss" scoped>
.quick-templates { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 16px; border-top: 1px solid #f5f5f5; flex-shrink: 0; }
.quick-tag { cursor: pointer; font-size: 12px; padding: 2px 10px; transition: transform 0.15s; }
.quick-tag:hover { transform: translateY(-1px); }
</style>
