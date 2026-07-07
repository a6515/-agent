<!-- Agent 实时活动面板 -->
<template>
  <div class="agent-activity-panel" v-if="activity.currentTool || activity.searchResult || activity.draftReady || activity.reviewResult || activity.refineResult">
    <transition-group name="ac-fade" tag="div" class="activity-cards">
      <!-- 检索 -->
      <div v-if="activity.searchResult" key="search" class="activity-card card-done">
        <div class="ac-header">
          <span class="ac-icon">🔍</span><span class="ac-title">检索范文</span>
          <a-tag color="success" size="small">完成</a-tag>
        </div>
        <div class="ac-body">
          检索到 <b>{{ activity.searchResult.totalFound }}</b> 篇范文
          <span v-if="activity.searchResult.exemplars && activity.searchResult.exemplars.length">
            ：{{ activity.searchResult.exemplars.map(e => e.source).join('、') }}
          </span>
        </div>
      </div>
      <!-- 初稿 -->
      <div v-if="activity.draftReady" key="draft" class="activity-card card-done">
        <div class="ac-header">
          <span class="ac-icon">✍️</span><span class="ac-title">撰写初稿</span>
          <a-tag color="success" size="small">完成</a-tag>
        </div>
        <div class="ac-body">初稿已生成，共 <b>{{ charCount }}</b> 字</div>
      </div>
      <!-- 格式审查 -->
      <div v-if="activity.reviewResult" key="review" class="activity-card"
        :class="activity.currentTool === 'check_format' ? 'card-running' : 'card-done'"
      >
        <div class="ac-header">
          <span class="ac-icon">✅</span>
          <span class="ac-title">格式审查 · 第 {{ activity.reviewResult.round }} 轮</span>
          <a-tag v-if="activity.currentTool === 'check_format'" color="processing" size="small">审查中</a-tag>
          <a-tag v-else :color="activity.reviewResult.criticalCount ? 'warning' : 'success'" size="small">
            {{ activity.reviewResult.criticalCount ? activity.reviewResult.criticalCount + ' 个问题' : '全部通过 ✓' }}
          </a-tag>
        </div>
        <div v-if="activity.reviewResult.issues && activity.reviewResult.issues.length" class="ac-checklist">
          <div v-for="item in activity.reviewResult.issues" :key="item.item" class="ac-check-row" :class="'ac-check-' + item.status">
            <span class="ac-check-mark">{{ item.status === 'pass' ? '✓' : item.status === 'issue' ? '✗' : '—' }}</span>
            <span class="ac-check-name">{{ item.item }}</span>
            <span v-if="item.detail" class="ac-check-detail">{{ item.detail }}</span>
          </div>
        </div>
        <div v-else class="ac-body">{{ activity.reviewResult.summary }}</div>
      </div>
      <!-- 定向精修 -->
      <div v-if="activity.refineResult" key="refine" class="activity-card"
        :class="activity.currentTool === 'refine_draft' ? 'card-running' : 'card-done'"
      >
        <div class="ac-header">
          <span class="ac-icon">🔧</span><span class="ac-title">定向精修</span>
          <a-tag v-if="activity.currentTool === 'refine_draft'" color="processing" size="small">修复中</a-tag>
          <a-tag v-else color="success" size="small">完成</a-tag>
        </div>
        <div class="ac-body">修改后草稿 <b>{{ activity.refineResult.charCount }}</b> 字</div>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
defineProps({ activity: { type: Object, required: true }, charCount: { type: Number, default: 0 } });
</script>

<style lang="scss" scoped>
.agent-activity-panel { padding: 10px 16px; border-bottom: 1px solid #f0f0f0; background: #fefefe; flex-shrink: 0; max-height: 240px; overflow-y: auto; }
.activity-cards { display: flex; flex-direction: column; gap: 8px; position: relative; }
.activity-card {
  background: #fff; border: 1px solid #e8ecf1; border-radius: 10px; padding: 10px 14px; transition: border-color 0.35s ease, box-shadow 0.35s ease, opacity 0.35s ease; box-shadow: 0 1px 3px rgba(0,0,0,0.03);
  &.card-done { opacity: 0.78; border-color: #e8ecf1; }
  &.card-running { border-color: #6b7cff; box-shadow: 0 0 0 3px rgba(107,124,255,0.10); opacity: 1; .ac-icon { animation: activityPulse 1.2s ease-in-out infinite; } }
  .ac-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; .ac-icon { font-size: 15px; } .ac-title { font-size: 13px; font-weight: 500; color: #444; } }
  .ac-body { font-size: 12px; color: #888; line-height: 1.5; padding-left: 23px; b { color: #555; } }
  .ac-checklist { padding-left: 23px; display: flex; flex-direction: column; gap: 2px; }
  .ac-check-row { display: flex; align-items: flex-start; gap: 5px; font-size: 12px; line-height: 1.5; padding: 2px 0;
    .ac-check-mark { flex-shrink: 0; width: 14px; text-align: center; font-weight: 600; }
    .ac-check-name { flex-shrink: 0; color: #555; min-width: 56px; } .ac-check-detail { color: #999; }
    &.ac-check-pass .ac-check-mark { color: #52c41a; } &.ac-check-issue { .ac-check-mark { color: #ff4d4f; } .ac-check-name { color: #ff4d4f; } } &.ac-check-na .ac-check-mark { color: #bbb; }
  }
}

/* 卡片淡入淡出 —— 出现时自下方浮入，消失时上移淡出，重排平滑过渡 */
.ac-fade-enter-active { transition: all 0.5s cubic-bezier(0.22, 1, 0.36, 1); }
.ac-fade-leave-active { transition: all 0.35s ease; position: absolute; width: calc(100% - 32px); }
.ac-fade-enter-from { opacity: 0; transform: translateY(12px) scale(0.97); }
.ac-fade-leave-to { opacity: 0; transform: translateY(-8px); }
.ac-fade-move { transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1); }

@keyframes activityPulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(1.15); } }
</style>
