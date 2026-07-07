<!--
  AI 智能公文创作 — 主容器组件 (Vue 3 + Pinia)
  状态管理：stores/ai.js (Pinia)
  SSE 解析：services/sse-client.js
  API 调用：services/api.js
-->
<template>
  <div class="ai-page">
    <TopHeader />
    <div class="ai-page-body">
      <div class="ai-workspace">
        <DraftPanel
          :content="store.draftContent" :title="store.draftTitle"
          :doc-type="store.draftDocType" :char-count="store.draftCharCount"
          :docx-path="store.draftDocxPath" :has-draft="store.hasDraft"
          :generating="store.activeMode === 'agent' && store.agentRunning"
          :disabled="store.agentRunning"
          :copying="store.copying" :downloading="store.downloading" :applying="store.applying"
          @copy="handleCopyContent" @download="handleDownloadDocx" @apply-to-oa="handleApplyToOA"
        />
        <ChatPanel
          :active-mode="store.activeMode" :messages="store.messages"
          :input-text="store.inputText" :generating="store.generating"
          :agent-running="store.agentRunning" :agent-question="store.agentQuestion"
          :agent-stages="store.agentStages" :percent="store.agentProgressPercent"
          :agent-activity="store.agentActivity" :char-count="store.draftCharCount"
          @switch-mode="switchMode" @template-select="t => store.inputText = t"
          @send="handleSend" @update:input-text="store.inputText = $event"
        />
      </div>
    </div>
    <BackendBanner :visible="store.backendOffline" />
    <AgentAskModal
      :visible="store.agentWaitingInput"
      :question="store.agentQuestion"
      :round="store.agentAskRound"
      :max="store.agentAskMax"
      :submitting="store.agentAskSubmitting"
      @submit="handleAgentAnswer"
      @skip="handleAgentSkip"
    />
    <FooterBar />
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useAiStore } from '../stores/ai';

import TopHeader from '../components/layout/TopHeader.vue';
import FooterBar from '../components/layout/FooterBar.vue';
import DraftPanel from '../components/draft/DraftPanel.vue';
import ChatPanel from '../components/chat/ChatPanel.vue';
import BackendBanner from '../components/common/BackendBanner.vue';
import AgentAskModal from '../components/agent/AgentAskModal.vue';

import { readSSEStream } from '../services/sse-client';
import { generateQuickStream, generateAgentStream, submitAgentAnswer, getDownloadUrl, getAbsoluteDownloadUrl } from '../services/api';

const store = useAiStore();
const abortCtrl = ref(null);

onBeforeUnmount(() => {
  if (abortCtrl.value) {
    abortCtrl.value.abort();
    abortCtrl.value = null;
  }
});

// ============================================================
// 模式切换
// ============================================================
function switchMode(targetMode) {
  if (targetMode === store.activeMode) return;
  if (store.generating) { message.warning('请等待当前生成完成后再切换模式'); return; }
  const doSwitch = () => {
    store.setMode(targetMode);
    message.success(`已切换到${targetMode === 'quick' ? '快速模式' : '深度模式'}`);
  };
  if (store.messages.length > 0) {
    Modal.confirm({
      title: '切换模式？',
      content: `切换到「${targetMode === 'quick' ? '快速模式' : '深度模式'}」将清空当前对话记录，正文草稿不受影响。`,
      okText: '确认切换', cancelText: '取消', onOk: doSwitch,
    });
  } else { doSwitch(); }
}

// ============================================================
// 发送消息路由
// ============================================================
function handleSend() {
  const text = store.inputText.trim();
  if (!text) return;
  // 补充信息由「动态弹窗」处理；生成中（含等待补充）输入框不接受发送
  if (store.generating) return;
  store.activeMode === 'quick' ? handleQuickSend(text) : handleAgentSend(text);
}

// ============================================================
// 快速模式
// ============================================================
async function handleQuickSend(text) {
  store.inputText = '';
  store.startGenerating('quick');
  store.addMessage('user', text);

  abortCtrl.value = new AbortController();
  let fullContent = '';

  try {
    const resp = await generateQuickStream(text, abortCtrl.value.signal);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const events = await readSSEStream(resp, (ev) => {
      if (ev.event === 'token') {
        fullContent += ev.data.token;
        store.updateDraft(fullContent, ev.data.doc_type);
      }
    });

    // 后处理 done / error
    let doneEv = null;
    for (const ev of events) {
      if (ev.event === 'done') {
        doneEv = ev;
        store.finalizeDraft(fullContent, ev.data.doc_type || store.draftDocType, ev.data.title, ev.data.docx_path);
      } else if (ev.event === 'error') {
        throw new Error(ev.data.error || '流式生成出错');
      }
    }

    store.addMessage('assistant',
      `已生成${store.draftDocType || '公文'}「${store.draftTitle}」，共 ${store.draftCharCount} 字。`);
    message.success('公文生成完成');
  } catch (err) {
    if (err.name !== 'AbortError') { console.error('[快速模式] 失败：', err); handleError(err); }
  } finally {
    store.inputText = '';
    store.stopGenerating();
    abortCtrl.value = null;
  }
}

// ============================================================
// 深度模式
// ============================================================
async function handleAgentSend(text) {
  store.inputText = '';
  store.startGenerating('agent');
  store.addMessage('user', text);

  const history = store.messages
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .slice(0, -1)
    .map(m => ({ role: m.role, content: m.content }));

  abortCtrl.value = new AbortController();

  try {
    const resp = await generateAgentStream(
      { prompt: text, history, currentDraft: store.hasDraft ? store.draftContent : null },
      abortCtrl.value.signal,
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    await readSSEStream(resp, (ev) => handleAgentEvent(ev));
  } catch (err) {
    if (err.name !== 'AbortError') { console.error('[深度模式] 失败：', err); handleError(err); }
  } finally {
    store.inputText = '';
    store.stopGenerating();
    abortCtrl.value = null;
  }
}

function handleAgentAnswer(answer) {
  const a = (answer || '').trim();
  if (!a) return;
  if (!store.agentSessionId) { handleError(new Error('会话 ID 丢失')); return; }
  // 补充问答只在弹窗内进行，不写入右侧对话区域
  store.markAskSubmitting();            // 弹窗进入“处理中”，由下一个事件决定推进下一轮 / 关闭
  submitAgentAnswer(store.agentSessionId, a).catch(err => {
    console.error('[Agent 回答] 失败：', err);
    store.clearAgentWaiting();
    handleError(err);
  });
}

// “由 AI 推断”：提交一个让 Agent 自行推断的答复，继续流程
function handleAgentSkip() {
  handleAgentAnswer('（此项我无法提供，请你根据常规情况合理推断后继续，不必再就此提问。）');
}

function handleAgentEvent(ev) {
  const d = ev.data || {};
  switch (ev.event) {
    case 'status':
      if (d.session_id) store.agentSessionId = d.session_id;
      store.onStatusMessage(d.message || '');
      break;
    case 'tool_start':
      if (store.agentWaitingInput) store.clearAgentWaiting();  // 用户已答、Agent 开始干活 → 关弹窗
      store.onToolStart(d.tool);
      break;
    case 'tool_end':
      store.updateActivity(d.tool, d);
      break;
    case 'draft':
      if (store.agentWaitingInput) store.clearAgentWaiting();  // Agent 已开始产出 → 关弹窗
      store.markDraftReady();          // 右侧活动卡标记「初稿已生成」
      // 深度模式：最终稿完成前不在左侧展示中间草稿，仅 done 时呈现最终稿
      break;
    case 'done':
      store.clearAgentWaiting();
      store.finalizeDraft(d.final_draft, d.doc_type, d.title, d.docx_path);
      store.markAllStagesDone();
      if (d.summary) {
        store.addMessage('assistant', `✅ ${d.summary}\n\n共进行 ${d.agent_turns || '?'} 轮自查，最终稿 ${store.draftCharCount} 字。`);
      }
      message.success('深度模式生成完成');
      break;
    case 'ask_user':
      store.setAgentWaiting(d.question || '');   // 只弹窗，不写入右侧对话
      if (d.session_id) store.agentSessionId = d.session_id;
      break;
    case 'error':
      store.clearAgentWaiting();
      store.addErrorMessage(d.message || 'Agent 运行出错');
      break;
  }
}

// ============================================================
// 草稿操作
// ============================================================
async function handleCopyContent() {
  if (!store.draftContent) { message.warning('没有可复制的正文内容'); return; }
  store.copying = true;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(store.draftContent);
    } else {
      const ta = document.createElement('textarea');
      ta.value = store.draftContent;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); document.body.removeChild(ta);
    }
    message.success('正文已复制到剪贴板');
  } catch (err) { message.error('复制失败'); }
  finally { store.copying = false; }
}

async function handleDownloadDocx() {
  if (!store.draftDocxPath) { message.warning('请先生成公文后再下载'); return; }
  store.downloading = true;
  try {
    const filename = store.draftDocxPath.split('\\').pop().split('/').pop();
    const link = document.createElement('a');
    link.href = getDownloadUrl(filename);
    link.download = filename;
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
    message.success('下载已开始');
  } catch (err) { message.error('下载失败'); }
  finally { store.downloading = false; }
}

async function handleApplyToOA() {
  if (!store.draftDocxPath) { message.warning('请先生成公文后再应用'); return; }
  if (!window.opener || window.opener.closed) { message.warning('未检测到 OA 发文页面，请从 OA 页面点击按钮进入'); return; }
  store.applying = true;
  try {
    const filename = store.draftDocxPath.split('\\').pop().split('/').pop();
    // 构造指向 AI 后端的绝对 URL，确保非同源的 OA 页面能正确下载
    // （不能用 window.location.origin：开发模式 AI 前端是 8081，下载端点在后端 8000，会 404）
    const downloadUrl = getAbsoluteDownloadUrl(filename);
    const resp = await fetch(downloadUrl);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    window.opener.postMessage({ type: 'AI_DOCX_APPLY', filename, docxUrl: downloadUrl, title: store.draftTitle, docType: store.draftDocType }, '*');
    message.success('已发送至 OA 发文页面');
  } catch (err) { message.error(`应用失败：${err.message}`); }
  finally { store.applying = false; }
}

// ============================================================
// 错误处理
// ============================================================
function handleError(err) {
  const msg = err.message || String(err);
  if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
    store.backendOffline = true;
    store.addErrorMessage('无法连接到 AI 后端服务，请确认后端已启动（http://localhost:8000）');
  } else {
    store.addErrorMessage(`生成失败：${msg}`);
  }
  message.error('生成失败');
}
</script>

<style lang="scss" scoped>
.ai-page { display: flex; flex-direction: column; height: 100vh; background: linear-gradient(160deg, #fbfcfd 0%, #eef1f5 55%, #e6eaf0 100%); overflow: hidden; }
.ai-page-body { flex: 1; overflow: hidden; padding: 16px; }
.ai-workspace { display: flex; height: 100%; gap: 16px; max-width: 1600px; margin: 0 auto; }
</style>
