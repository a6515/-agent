<!-- 对话输入区 -->
<template>
  <div class="chat-input-area">
    <div class="input-row">
      <a-textarea
        v-model:value="inputVal"
        :placeholder="placeholder"
        :autoSize="{ minRows: 1, maxRows: 4 }"
        :disabled="disabled"
        class="chat-textarea"
        @pressEnter="onEnter"
      />
      <a-button type="primary" shape="circle" size="large"
        :loading="loading" :disabled="!inputVal || !inputVal.trim() || disabled"
        @click="onSend" class="send-btn"
      >
        <span v-if="!loading">↑</span>
      </a-button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '请输入您的公文需求...' },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue', 'send']);

// 本地镜像值，作为 a-textarea v-model:value 的绑定目标
const inputVal = ref(props.modelValue);

// 父组件修改 prop → 同步到本地（用于 store.inputText = '' 清空）
watch(() => props.modelValue, (v) => {
  inputVal.value = v;
});

// 本地值变化 → 同步到父组件
watch(inputVal, (v) => {
  emit('update:modelValue', v);
});

function onSend() {
  const v = inputVal.value;
  if (!v || !v.trim() || props.disabled) return;
  emit('send');
}
function onEnter(e) {
  if (!e.shiftKey) { e.preventDefault(); onSend(); }
}
</script>

<style lang="scss" scoped>
.chat-input-area { border-top: 1px solid #eee; padding: 12px 16px; flex-shrink: 0; background: #fff; }
.input-row { display: flex; align-items: flex-end; gap: 8px; }
.chat-textarea { flex: 1;
  :deep(textarea) { border-radius: 8px !important; border: 1px solid #e8e8e8 !important; font-size: 14px; padding: 10px 12px !important; resize: none !important; transition: border-color 0.2s;
    &:focus { border-color: #667eea !important; box-shadow: 0 0 0 2px rgba(102,126,234,0.1) !important; }
  }
}
.send-btn { flex-shrink: 0; width: 40px; height: 40px; background: linear-gradient(135deg, #667eea, #764ba2); border: none; display: flex; align-items: center; justify-content: center;
  &:hover { opacity: 0.9; box-shadow: 0 3px 10px rgba(102,126,234,0.35); }
  &:disabled { background: #d9d9d9 !important; }
  span { font-size: 18px; color: #fff; }
}
</style>
