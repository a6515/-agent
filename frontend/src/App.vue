<template>
  <div id="ai-app-root">
    <AiGenerator />
  </div>
</template>

<script setup>
import AiGenerator from './views/AiGenerator.vue';
</script>

<style lang="scss">
#ai-app-root { min-height: 100vh; background: linear-gradient(160deg, #fbfcfd 0%, #eef1f5 55%, #e6eaf0 100%); }
</style>
