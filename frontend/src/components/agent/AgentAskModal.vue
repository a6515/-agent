<!-- Agent 逐轮补充信息 · 动态液态玻璃弹窗 -->
<template>
  <transition name="ask-pop">
    <div v-if="visible" class="ask-overlay">
      <div class="ask-modal">
        <div class="ask-sheen"></div>
        <div class="ask-body">
          <div class="ask-header">
            <span class="ask-icon">🤔</span>
            <span class="ask-title">补充信息</span>
            <span class="ask-round">第 {{ round }} / {{ max }} 轮</span>
          </div>

          <div class="ask-question">{{ question }}</div>

          <textarea
            ref="inputRef"
            v-model="answer"
            class="ask-textarea"
            :placeholder="submitting ? 'Agent 正在思考…' : '在此输入您的补充（Enter 提交，Shift+Enter 换行）'"
            :disabled="submitting"
            rows="3"
            @keydown="onKeydown"
          ></textarea>

          <div class="ask-actions">
            <button class="ask-btn ask-skip" :disabled="submitting" @click="onSkip">由 AI 推断</button>
            <button class="ask-btn ask-submit" :disabled="submitting || !answer.trim()" @click="onSubmit">
              <span v-if="!submitting">提交并继续</span>
              <span v-else class="ask-spinner"></span>
            </button>
          </div>

          <div class="ask-hint">Agent 会逐项询问，最多 {{ max }} 轮；问满后将基于已有信息自动撰写。</div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';

const props = defineProps({
  visible: { type: Boolean, default: false },
  question: { type: String, default: '' },
  round: { type: Number, default: 1 },
  max: { type: Number, default: 3 },
  submitting: { type: Boolean, default: false },
});
const emit = defineEmits(['submit', 'skip']);

const answer = ref('');
const inputRef = ref(null);

// 新问题到来（轮次变化）→ 清空输入并聚焦
watch(() => props.round, () => {
  answer.value = '';
  nextTick(() => inputRef.value?.focus());
});
watch(() => props.visible, (v) => {
  if (v) nextTick(() => inputRef.value?.focus());
});

function onSubmit() {
  const v = answer.value.trim();
  if (props.submitting || !v) return;
  emit('submit', v);
}
function onSkip() {
  if (props.submitting) return;
  emit('skip');
}
function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    onSubmit();
  }
}
</script>

<style lang="scss" scoped>
.ask-overlay {
  position: fixed; inset: 0; z-index: 1200;
  display: flex; align-items: center; justify-content: center; padding: 20px;
  background: rgba(20, 27, 45, 0.26);
  -webkit-backdrop-filter: blur(5px); backdrop-filter: blur(5px);
}
/* 弹窗主体：液态玻璃 */
.ask-modal {
  position: relative; width: 440px; max-width: 100%;
  border-radius: 18px; overflow: hidden;
  background: linear-gradient(135deg, rgba(255,255,255,0.82) 0%, rgba(238,241,246,0.7) 100%);
  -webkit-backdrop-filter: blur(30px) saturate(190%); backdrop-filter: blur(30px) saturate(190%);
  border: 1px solid rgba(255,255,255,0.7);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), 0 24px 60px rgba(23,31,50,0.22);
}
.ask-sheen {
  position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(120deg, rgba(255,255,255,0.42) 0%, rgba(255,255,255,0) 44%);
}
.ask-body { position: relative; z-index: 1; padding: 22px 22px 16px; }

.ask-header { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.ask-icon { font-size: 18px; }
.ask-title { font-size: 16px; font-weight: 600; color: #2a3242; letter-spacing: 0.3px; }
.ask-round {
  margin-left: auto; font-size: 11px; font-weight: 600; color: #6b7688;
  padding: 2px 9px; border-radius: 999px;
  background: rgba(255,255,255,0.6); border: 1px solid rgba(120,130,150,0.20);
}

.ask-question {
  font-size: 14px; line-height: 1.65; color: #3a4250;
  padding: 12px 14px; margin-bottom: 14px;
  background: rgba(255,255,255,0.5); border: 1px solid rgba(120,130,150,0.16);
  border-radius: 12px; word-break: break-word;
}

.ask-textarea {
  width: 100%; box-sizing: border-box; resize: none; font-family: inherit;
  padding: 10px 12px; font-size: 14px; line-height: 1.6; color: #2a3242;
  background: rgba(255,255,255,0.72); border: 1px solid rgba(120,130,150,0.28);
  border-radius: 10px; outline: none; transition: border-color 0.2s, box-shadow 0.2s;
  &::placeholder { color: #a0a8b5; }
  &:focus { border-color: #8aa0c8; box-shadow: 0 0 0 3px rgba(120,150,200,0.15); }
  &:disabled { opacity: 0.7; }
}

.ask-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.ask-btn {
  height: 34px; padding: 0 16px; font-size: 13px; font-weight: 600;
  border-radius: 999px; cursor: pointer; transition: all 0.18s; border: 1px solid transparent;
  display: inline-flex; align-items: center; justify-content: center; min-width: 88px;
  &:disabled { cursor: not-allowed; opacity: 0.55; }
}
.ask-skip {
  color: #5f6b7d; background: rgba(255,255,255,0.55); border-color: rgba(120,130,150,0.24);
  &:not(:disabled):hover { background: rgba(255,255,255,0.9); }
}
.ask-submit {
  color: #fff; background: linear-gradient(135deg, #3d4657 0%, #2a3242 100%);
  box-shadow: 0 4px 12px rgba(42,50,66,0.25);
  &:not(:disabled):hover { box-shadow: 0 6px 16px rgba(42,50,66,0.32); transform: translateY(-1px); }
}
.ask-spinner {
  width: 15px; height: 15px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff;
  animation: askspin 0.7s linear infinite;
}
@keyframes askspin { to { transform: rotate(360deg); } }

.ask-hint { margin-top: 12px; font-size: 11px; color: #98a1b0; text-align: center; }

/* 弹入/弹出动画 */
.ask-pop-enter-active, .ask-pop-leave-active { transition: opacity 0.22s ease; }
.ask-pop-enter-from, .ask-pop-leave-to { opacity: 0; }
.ask-pop-enter-active .ask-modal { transition: transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1); }
.ask-pop-enter-from .ask-modal { transform: translateY(14px) scale(0.96); }
</style>
