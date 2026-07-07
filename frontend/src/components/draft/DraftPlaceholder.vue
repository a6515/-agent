<!-- 草稿面板空状态占位 -->
<template>
  <div class="draft-placeholder">
    <div class="placeholder-icon">📄</div>
    <div class="placeholder-title">公文正文预览</div>
    <div class="placeholder-desc">在右侧输入公文需求，AI 生成的正文将在此实时展示</div>
    <div class="placeholder-tips">
      <div class="tip-item">✨ 支持 10 种公文体裁</div>
      <div class="tip-item">🔍 基于 RAG 知识库检索范文</div>
      <div class="tip-item">📝 一键回写致远 OA 编辑器</div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.draft-placeholder {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 48px 32px; text-align: center; background: linear-gradient(180deg, #fafbff 0%, #fff 100%);
  .placeholder-icon { font-size: 56px; margin-bottom: 16px; opacity: 0.6; }
  .placeholder-title { font-size: 18px; font-weight: 600; color: #333; margin-bottom: 8px; }
  .placeholder-desc { font-size: 13px; color: #999; margin-bottom: 24px; line-height: 1.6; }
  .placeholder-tips { display: flex; flex-direction: column; gap: 8px; }
  .tip-item { font-size: 13px; color: #888; padding: 8px 16px; background: #f5f7ff; border-radius: 6px; }
}
</style>
