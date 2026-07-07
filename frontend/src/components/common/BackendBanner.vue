<!-- 后端断联提示 -->
<template>
  <div class="backend-banner" v-if="visible">
    <a-alert
      message="无法连接到 AI 后端服务"
      description="请确保 Python 后端已启动：python scripts/run_api.py → http://localhost:8000"
      type="warning" showIcon banner
    />
  </div>
</template>

<script setup>
defineProps({ visible: { type: Boolean, default: false } });
</script>

<style lang="scss" scoped>
.backend-banner { flex-shrink: 0; padding: 0 16px 8px; max-width: 1600px; margin: 0 auto; width: 100%; }
</style>
