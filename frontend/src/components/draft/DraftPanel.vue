<!-- 左侧：正文预览面板 -->
<template>
  <div class="draft-panel">
    <div v-if="generating" class="draft-generating">
      <div class="gen-spinner"></div>
      <div class="gen-title">AI 正在创作公文…</div>
      <div class="gen-desc">正在检索范文、撰写并逐项自查格式，请稍候</div>
    </div>
    <DraftPlaceholder v-else-if="!hasDraft" />
    <div v-else class="draft-content">
      <div class="draft-meta">
        <div class="meta-left">
          <a-tag :color="docTypeColor">{{ docType || '公文' }}</a-tag>
          <span class="meta-title">{{ title || '（未提取到标题）' }}</span>
        </div>
        <div class="meta-right"><span class="meta-chars">{{ charCount }} 字</span></div>
      </div>
      <div class="draft-scroll"><pre class="draft-text">{{ content }}</pre></div>
      <div class="draft-actions">
        <a-button size="large" @click="$emit('copy')" :loading="copying" :disabled="disabled">📋 {{ copying ? '复制中...' : '复制正文' }}</a-button>
        <a-button size="large" @click="$emit('download')" :loading="downloading" :disabled="!docxPath || disabled">📥 下载 docx</a-button>
        <a-button type="primary" size="large" @click="$emit('apply-to-oa')" :loading="applying" :disabled="!docxPath || disabled" style="background:#52c41a;border-color:#52c41a">
          📝 {{ applying ? '应用中...' : '应用此正文' }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import DraftPlaceholder from './DraftPlaceholder.vue';
import { DOC_TYPE_COLORS } from '../../constants';

const props = defineProps({
  content: { type: String, default: '' }, title: { type: String, default: '' },
  docType: { type: String, default: '' }, charCount: { type: Number, default: 0 },
  docxPath: { type: String, default: '' }, hasDraft: { type: Boolean, default: false },
  generating: { type: Boolean, default: false }, disabled: { type: Boolean, default: false },
  copying: { type: Boolean, default: false }, downloading: { type: Boolean, default: false },
  applying: { type: Boolean, default: false },
});
defineEmits(['copy', 'download', 'apply-to-oa']);

const docTypeColor = computed(() => DOC_TYPE_COLORS[props.docType] || 'default');
</script>

<style lang="scss" scoped>
.draft-panel { flex: 0.52; display: flex; flex-direction: column; background: #fff; border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); overflow: hidden; }
.draft-generating {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 48px 32px; text-align: center; background: linear-gradient(180deg, #fafbff 0%, #fff 100%);
  .gen-spinner { width: 42px; height: 42px; border-radius: 50%; border: 3px solid #e6eaf2; border-top-color: #8aa0c8; animation: genspin 0.8s linear infinite; margin-bottom: 18px; }
  .gen-title { font-size: 16px; font-weight: 600; color: #3a4250; margin-bottom: 8px; }
  .gen-desc { font-size: 13px; color: #98a1b0; line-height: 1.6; }
}
@keyframes genspin { to { transform: rotate(360deg); } }
.draft-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.draft-meta { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #fafafa; border-bottom: 1px solid #f0f0f0; flex-shrink: 0;
  .meta-left { display: flex; align-items: center; gap: 10px; overflow: hidden;
    .meta-title { font-size: 15px; font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px; }
  }
  .meta-right .meta-chars { font-size: 13px; color: #999; }
}
.draft-scroll { flex: 1; overflow-y: auto; padding: 24px 28px;
  .draft-text { white-space: pre-wrap; word-break: break-all; font-family: '仿宋','FangSong','STFangsong','KaiTi','SimSun',serif; font-size: 16px; line-height: 2; color: #333; margin: 0; background: #fffdf7; padding: 28px 32px; border: 1px solid #f0e6d3; border-radius: 4px; min-height: 200px; }
}
.draft-actions { display: flex; justify-content: center; gap: 12px; padding: 14px 20px; border-top: 1px solid #f0f0f0; background: #fafafa; flex-shrink: 0; flex-wrap: wrap;
  .ant-btn { border-radius: 6px; min-width: 110px; }
}
</style>
