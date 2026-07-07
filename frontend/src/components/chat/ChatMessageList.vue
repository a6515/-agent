<!-- 聊天消息列表 -->
<template>
  <div class="chat-messages">
    <!-- 欢迎语 -->
    <div v-if="messages.length === 0" class="chat-welcome">
      <div class="welcome-avatar">🤖</div>
      <div class="welcome-text">
        <template v-if="mode === 'quick'">
          <div class="welcome-title">快速模式</div>
          <div class="welcome-desc">输入公文需求，AI 将检索范文并一次生成全文。<br>适合简单明确的公文，~3 秒出稿。</div>
        </template>
        <template v-else>
          <div class="welcome-title">深度模式</div>
          <div class="welcome-desc">AI 会先检索范文、撰写初稿、然后逐项自查格式并自动修复。<br>适合格式要求严格的公文，~15-30 秒出稿。</div>
        </template>
      </div>
    </div>

    <!-- 消息列表 -->
    <div v-for="msg in messages" :key="msg.id" class="chat-msg" :class="[`msg-${msg.role}`]">
      <!-- 系统消息 -->
      <div v-if="msg.role === 'system'" class="msg-system">
        <span class="sys-icon">{{ msg.icon || 'ℹ️' }}</span>
        <span class="sys-text">{{ msg.content }}</span>
      </div>
      <!-- 用户消息 -->
      <div v-else-if="msg.role === 'user'" class="msg-user">
        <div class="msg-bubble user-bubble">{{ msg.content }}</div>
      </div>
      <!-- 助手消息 -->
      <div v-else-if="msg.role === 'assistant'" class="msg-assistant">
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble assistant-bubble">{{ msg.content }}</div>
      </div>
      <!-- 工具消息 -->
      <div v-else-if="msg.role === 'tool'" class="msg-tool">
        <div class="tool-card">
          <div class="tool-header">
            <span class="tool-icon">{{ TOOL_ICONS[msg.toolName] || '🔧' }}</span>
            <span class="tool-name">{{ TOOL_LABELS[msg.toolName] || msg.toolName }}</span>
            <a-tag :color="msg.status === 'running' ? 'processing' : msg.status === 'error' ? 'error' : 'success'" size="small" style="margin-left:8px">
              {{ msg.status === 'running' ? '执行中' : msg.status === 'error' ? '失败' : '完成' }}
            </a-tag>
          </div>
          <div v-if="msg.detail" class="tool-body">{{ msg.detail }}</div>
          <div v-if="msg.checkItems && msg.checkItems.length" class="tool-checklist">
            <div v-for="item in msg.checkItems" :key="item.item" class="check-item" :class="`check-${item.status}`">
              <span class="check-mark">{{ item.status === 'pass' ? '✓' : item.status === 'issue' ? '✗' : '—' }}</span>
              <span class="check-name">{{ item.item }}</span>
              <span v-if="item.detail" class="check-detail">{{ item.detail }}</span>
            </div>
          </div>
        </div>
      </div>
      <!-- 错误消息 -->
      <div v-else-if="msg.role === 'error'" class="msg-error">
        <a-alert :message="msg.content" type="error" showIcon closable />
      </div>
    </div>

    <!-- 打字指示器 -->
    <div v-if="typing" class="chat-typing">
      <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
    </div>
    <div ref="chatBottom"></div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';
import { TOOL_ICONS, TOOL_LABELS } from '../../constants';

const props = defineProps({
  messages: { type: Array, default: () => [] },
  mode: { type: String, default: 'quick' },
  typing: { type: Boolean, default: false },
});

const chatBottom = ref(null);

watch(() => props.messages, () => {
  nextTick(() => {
    chatBottom.value?.scrollIntoView({ behavior: 'smooth' });
  });
}, { deep: true });
</script>

<style lang="scss" scoped>
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; background: linear-gradient(160deg, #fbfcfd 0%, #f3f5f8 100%); }
.chat-welcome { display: flex; gap: 14px; padding: 24px 12px; align-items: flex-start;
  .welcome-avatar { font-size: 40px; flex-shrink: 0; }
  .welcome-text { .welcome-title { font-size: 16px; font-weight: 600; color: #333; margin-bottom: 6px; } .welcome-desc { font-size: 13px; color: #888; line-height: 1.7; } }
}
.msg-system { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 4px 0;
  .sys-icon { font-size: 14px; } .sys-text { font-size: 12px; color: #aaa; background: #f0f0f0; padding: 4px 12px; border-radius: 10px; }
}
.msg-user { display: flex; justify-content: flex-end; }
.user-bubble {
  background: linear-gradient(135deg, rgba(255,255,255,0.55) 0%, rgba(240,243,247,0.34) 100%);
  -webkit-backdrop-filter: blur(18px) saturate(180%);
  backdrop-filter: blur(18px) saturate(180%);
  border: 1px solid rgba(140,150,170,0.20);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.85), 0 4px 14px rgba(23,31,50,0.07);
  color: #2a3242; padding: 10px 16px; border-radius: 16px 16px 4px 16px;
  font-size: 14px; line-height: 1.6; max-width: 80%; word-break: break-word;
}
.msg-assistant { display: flex; gap: 8px; align-items: flex-start; .msg-avatar { font-size: 22px; flex-shrink: 0; margin-top: 6px; } }
.assistant-bubble { background: #fff; border: 1px solid #eee; padding: 10px 14px; border-radius: 4px 16px 16px 16px; font-size: 14px; line-height: 1.6; color: #333; max-width: 85%; word-break: break-word; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.msg-tool { display: flex; padding-left: 30px; }
.tool-card { background: #fff; border: 1px solid #e8ecf1; border-radius: 8px; padding: 10px 14px; width: 100%; box-shadow: 0 1px 3px rgba(0,0,0,0.03);
  .tool-header { display: flex; align-items: center; .tool-icon { font-size: 16px; margin-right: 6px; } .tool-name { font-size: 13px; font-weight: 500; color: #555; } }
  .tool-body { margin-top: 6px; font-size: 13px; color: #777; line-height: 1.5; }
  .tool-checklist { margin-top: 8px;
    .check-item { display: flex; align-items: flex-start; gap: 6px; padding: 4px 0; font-size: 12px; line-height: 1.5;
      .check-mark { flex-shrink: 0; width: 16px; text-align: center; } .check-name { flex-shrink: 0; color: #555; min-width: 60px; } .check-detail { color: #999; }
      &.check-pass .check-mark { color: #52c41a; } &.check-issue { .check-mark { color: #ff4d4f; } .check-name { color: #ff4d4f; } } &.check-na .check-mark { color: #bbb; }
    }
  }
}
.msg-error { padding: 0; :deep(.ant-alert) { font-size: 13px; } }
.chat-typing { display: flex; gap: 4px; padding: 8px 16px;
  .typing-dot { width: 7px; height: 7px; background: #bbb; border-radius: 50%; animation: typingBounce 1.2s infinite ease-in-out;
    &:nth-child(2) { animation-delay: 0.15s; } &:nth-child(3) { animation-delay: 0.3s; } }
}
@keyframes typingBounce { 0%, 60%, 100% { transform: translateY(0); opacity: 0.4; } 30% { transform: translateY(-6px); opacity: 1; } }
</style>
