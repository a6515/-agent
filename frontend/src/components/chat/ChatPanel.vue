<!-- 右侧：对话交互面板 -->
<template>
  <div class="chat-panel">
    <ModeTabs :active="activeMode" @switch="$emit('switch-mode', $event)" />
    <AgentProgressBar v-if="activeMode === 'agent' && agentRunning" :stages="agentStages" :percent="percent" />
    <AgentActivityCard v-if="activeMode === 'agent' && agentRunning" :activity="agentActivity" :char-count="charCount" />
    <ChatMessageList :messages="messages" :mode="activeMode" :typing="generating && !agentRunning" />
    <QuickTemplates v-if="activeMode === 'quick' && !agentRunning" @select="$emit('template-select', $event)" />
    <ChatInput
      :model-value="inputText"
      @update:model-value="$emit('update:inputText', $event)"
      :placeholder="inputPlaceholder"
      :disabled="generating"
      :loading="generating"
      @send="$emit('send')"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue';
import ModeTabs from './ModeTabs.vue';
import ChatMessageList from './ChatMessageList.vue';
import ChatInput from './ChatInput.vue';
import QuickTemplates from './QuickTemplates.vue';
import AgentProgressBar from '../agent/AgentProgressBar.vue';
import AgentActivityCard from '../agent/AgentActivityCard.vue';

const props = defineProps({
  activeMode: { type: String, default: 'quick' }, messages: { type: Array, default: () => [] },
  inputText: { type: String, default: '' }, generating: { type: Boolean, default: false },
  agentRunning: { type: Boolean, default: false }, agentQuestion: { type: String, default: '' },
  agentStages: { type: Array, default: () => [] }, percent: { type: Number, default: 0 },
  agentActivity: { type: Object, default: () => ({}) }, charCount: { type: Number, default: 0 },
});
defineEmits(['switch-mode', 'template-select', 'send', 'update:inputText']);

const inputPlaceholder = computed(() => {
  if (props.generating) return 'AI 正在创作中...';
  if (props.activeMode === 'agent') return '描述您的公文需求，Agent 将多轮自查自修...';
  return '例如：写一份关于申请购买3台服务器的请示';
});
</script>

<style lang="scss" scoped>
.chat-panel { flex: 0.48; display: flex; flex-direction: column; background: #fff; border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); overflow: hidden; }
</style>
