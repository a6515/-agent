<!-- 快速/深度模式切换 -->
<template>
  <div class="mode-tabs">
    <div class="mode-tab" :class="{ active: active === 'quick' }" @click="$emit('switch', 'quick')">
      <span class="mode-icon">⚡</span>
      <span class="mode-label">快速模式</span>
      <span class="mode-desc">单次生成</span>
    </div>
    <div class="mode-tab" :class="{ active: active === 'agent' }" @click="$emit('switch', 'agent')">
      <span class="mode-icon">☀️</span>
      <span class="mode-label">深度模式</span>
      <span class="mode-desc">多轮自查</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ active: { type: String, default: 'quick' } });
defineEmits(['switch']);
</script>

<style lang="scss" scoped>
.mode-tabs { display: flex; border-bottom: 1px solid #f0f0f0; flex-shrink: 0; }
.mode-tab {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 12px 16px; cursor: pointer; transition: all 0.2s;
  border-bottom: 2px solid transparent; position: relative; user-select: none;
  &:hover { background: #fafbff; }
  &.active {
    border-bottom-color: #667eea; background: #f5f7ff;
    .mode-label { color: #667eea; font-weight: 600; }
    .mode-desc { color: rgba(102,126,234,0.6); }
  }
  .mode-icon { font-size: 18px; }
  .mode-label { font-size: 15px; color: #333; }
  .mode-desc { font-size: 11px; color: #bbb; }
}
</style>
