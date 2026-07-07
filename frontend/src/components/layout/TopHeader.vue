<!-- 顶部导航栏 -->
<template>
  <div class="top-header">
    <div class="header-inner">
      <div class="header-left">
        <span class="brand-mark">文</span>
        <span class="header-title">AI 智能公文创作</span>
        <span class="version-pill">v2.0</span>
      </div>
      <div class="header-right">
        <span class="model-badge">
          <span class="badge-dot"></span>
          DeepSeek
        </span>
        <span class="header-hint">RAG 知识库 + 大模型 · GB/T 9704-2012</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
/* ============================================================
   顶部栏：灰白「液态玻璃」质感
   半透明灰白底 + 背景模糊/高饱和 + 顶部高光边 + 斜向反光 + 柔投影
   ============================================================ */
.top-header {
  position: relative;
  flex-shrink: 0;
  z-index: 100;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.5) 0%, rgba(243, 245, 249, 0.28) 100%);
  backdrop-filter: blur(24px) saturate(190%);
  -webkit-backdrop-filter: blur(24px) saturate(190%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),   /* 顶部高光边——玻璃受光的亮边 */
    0 8px 28px rgba(23, 31, 50, 0.06);        /* 底部柔和投影——悬浮感 */
}
/* 斜向反光——液态玻璃的镜面高光 */
.top-header::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(105deg, rgba(255, 255, 255, 0.38) 0%, rgba(255, 255, 255, 0) 40%);
}

.header-inner {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
}
.header-left { display: flex; align-items: center; gap: 10px; }

/* 品牌标记：灰白玻璃小方块 + “文” */
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  font-size: 15px;
  font-weight: 700;
  color: #4a5568;
  background: linear-gradient(145deg, #ffffff 0%, #e9edf3 100%);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 2px 6px rgba(23, 31, 50, 0.10), inset 0 1px 0 #fff;
}
.header-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: #2a3242;
}
.version-pill {
  font-size: 11px;
  font-weight: 600;
  color: #6b7688;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(120, 130, 150, 0.20);
}

.header-right { display: flex; align-items: center; gap: 12px; }
/* 模型徽标：玻璃胶囊 + 在线小圆点 */
.model-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #3a4250;
  font-size: 12px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(120, 130, 150, 0.18);
  padding: 3px 11px;
  border-radius: 999px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}
.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: linear-gradient(135deg, #34d399, #10b981);
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15);
}
.header-hint { color: #98a1b0; font-size: 12px; }

@media (max-width: 640px) {
  .header-hint { display: none; }
}
</style>
