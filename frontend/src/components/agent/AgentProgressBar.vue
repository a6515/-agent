<!-- Agent 深度模式进度追踪器 —— 步骤指示器（节点旅程 + 呼吸光点，替代线性进度条） -->
<template>
  <div class="agent-stepper">
    <div class="stepper-row">
      <template v-for="(stage, i) in stages" :key="stage.key">
        <div v-if="i > 0" class="stepper-connector" :class="{ filled: stages[i - 1].status === 'done' }"></div>
        <div class="stepper-node" :class="'is-' + stage.status">
          <div class="node-circle">
            <span v-if="stage.status === 'done'" class="node-check">✓</span>
            <span v-else class="node-emoji">{{ stage.icon }}</span>
            <span class="node-halo"></span>
          </div>
          <div class="node-label">{{ stage.label }}</div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
defineProps({ stages: { type: Array, required: true }, percent: { type: Number, default: 0 } });
</script>

<style lang="scss" scoped>
.agent-stepper {
  padding: 16px 14px 12px;
  background: linear-gradient(180deg, #fcfdff 0%, #f5f7fc 100%);
  border-bottom: 1px solid #eef0f4;
  flex-shrink: 0;
}
.stepper-row { display: flex; align-items: flex-start; }

.stepper-node {
  display: flex; flex-direction: column; align-items: center; gap: 7px;
  flex-shrink: 0; width: 46px;
}
.node-circle {
  position: relative; width: 30px; height: 30px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 14px;
  background: #eef0f4; color: #a8adb8; border: 1.5px solid #e3e6eb;
  transition: all 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}
.node-emoji { opacity: 0.5; filter: grayscale(0.55); transition: all 0.3s ease; }
.node-check { font-size: 15px; font-weight: 700; line-height: 1; }
.node-label {
  font-size: 11px; color: #b0b5c0; white-space: nowrap;
  letter-spacing: 0.2px; transition: color 0.35s ease;
}

/* 连接线：前一步完成即点亮 */
.stepper-connector {
  flex: 1; height: 2px; margin-top: 15px; background: #e3e6eb;
  border-radius: 1px; transition: background 0.5s ease;
}
.stepper-connector.filled { background: #c2cef2; }

/* 完成态 */
.is-done {
  .node-circle { background: #edf1ff; border-color: #c8d3f7; color: #5f74d8; }
  .node-label { color: #8a92a4; }
}

/* 进行态 —— 呼吸光点 */
.is-active {
  .node-circle {
    background: #fff; border-color: #6b7cff; color: #5468e0;
    box-shadow: 0 3px 10px rgba(107, 124, 255, 0.28);
    transform: scale(1.1);
  }
  .node-emoji { opacity: 1; filter: none; }
  .node-label { color: #5468e0; font-weight: 600; }
  .node-halo { animation: haloBreath 1.9s ease-out infinite; }
}
.node-halo {
  position: absolute; inset: -3px; border-radius: 50%;
  border: 2px solid #6b7cff; opacity: 0; pointer-events: none;
}
@keyframes haloBreath {
  0% { transform: scale(0.92); opacity: 0.5; }
  70% { transform: scale(1.55); opacity: 0; }
  100% { transform: scale(1.55); opacity: 0; }
}
</style>
