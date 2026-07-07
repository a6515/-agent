/**
 * Pinia 状态管理 — AI 公文创作全局共享状态
 */
import { defineStore } from 'pinia';
import { AGENT_STAGES } from '../constants';

let _msgId = 0;
function nextMsgId() {
  return `msg_${Date.now()}_${++_msgId}`;
}

function makeDefaultStages() {
  return AGENT_STAGES.map(s => ({ ...s, status: 'pending' }));
}

function makeDefaultActivity() {
  return {
    currentTool: null,
    searchResult: null,
    draftReady: false,
    reviewResult: null,
    refineResult: null,
    reviewRound: 0,
  };
}

export const useAiStore = defineStore('ai', {
  state: () => ({
    // ========== 模式 ==========
    activeMode: 'quick',

    // ========== 聊天 ==========
    messages: [],
    inputText: '',

    // ========== 草稿 ==========
    draftContent: '',
    draftTitle: '',
    draftDocType: '',
    draftCharCount: 0,
    draftDocxPath: '',
    hasDraft: false,

    // ========== 生成状态 ==========
    generating: false,
    agentRunning: false,
    agentWaitingInput: false,
    agentQuestion: '',
    agentAskRound: 0,        // 当前补充提问轮次（1~3）
    agentAskMax: 3,          // 最多提问轮次
    agentAskSubmitting: false, // 用户已提交答案、等待 Agent 处理下一步
    agentSessionId: null,
    backendOffline: false,

    // ========== 操作状态 ==========
    copying: false,
    downloading: false,
    applying: false,

    // ========== Agent 进度 ==========
    agentStages: makeDefaultStages(),

    // ========== Agent 活动面板 ==========
    agentActivity: makeDefaultActivity(),
  }),

  getters: {
    agentProgressPercent() {
      const done = this.agentStages.filter(s => s.status === 'done').length;
      return Math.round((done / this.agentStages.length) * 100);
    },

    hasAgentActivity() {
      const a = this.agentActivity;
      return a.currentTool || a.searchResult || a.draftReady || a.reviewResult || a.refineResult;
    },
  },

  actions: {
    // ---- 模式 ----
    setMode(mode) {
      this.activeMode = mode;
      this.messages = [];
      this.agentSessionId = null;
      this.agentWaitingInput = false;
      this.agentQuestion = '';
      this.agentAskRound = 0;
      this.agentAskSubmitting = false;
    },

    // ---- 草稿 ----
    updateDraft(content, docType) {
      if (!content) return;
      this.draftContent = content;
      this.draftCharCount = content.length;
      this.hasDraft = true;
      if (docType) this.draftDocType = docType;
      if (!this.draftTitle) {
        this.draftTitle = extractTitle(content);
      }
    },

    finalizeDraft(content, docType, title, docxPath) {
      if (content) {
        this.draftContent = content;
        this.draftCharCount = content.length;
        this.hasDraft = true;
      }
      if (docType) this.draftDocType = docType;
      if (title) this.draftTitle = title;
      else if (content && !this.draftTitle) this.draftTitle = extractTitle(content);
      if (docxPath) this.draftDocxPath = docxPath;
    },

    // ---- 消息 ----
    addMessage(role, content, extra = {}) {
      this.messages.push({ id: nextMsgId(), role, content, ...extra });
    },

    addErrorMessage(content) {
      this.messages.push({ id: nextMsgId(), role: 'error', content });
    },

    // ---- 生成状态 ----
    startGenerating(mode) {
      this.generating = true;
      this.backendOffline = false;
      if (mode === 'agent') {
        this.agentRunning = true;
        this.agentWaitingInput = false;
        this.agentAskRound = 0;
        this.agentAskSubmitting = false;
        this.resetAgentStages();
        this.setAgentStage('analyze');
        this.agentActivity = makeDefaultActivity();
      }
    },

    stopGenerating() {
      this.generating = false;
      if (this.agentRunning) {
        this.agentRunning = false;
        setTimeout(() => this.resetAgentStages(), 2000);
      }
    },

    setAgentWaiting(question) {
      this.agentWaitingInput = true;
      this.agentQuestion = question;
      this.agentAskRound += 1;         // 每收到一次提问推进一轮
      this.agentAskSubmitting = false;
    },

    markAskSubmitting() {
      this.agentAskSubmitting = true;  // 用户已提交，弹窗进入“处理中”，等待下一个事件
    },

    clearAgentWaiting() {
      this.agentWaitingInput = false;
      this.agentQuestion = '';
      this.agentAskSubmitting = false;
    },

    // ---- Agent 阶段 ----
    setAgentStage(stageKey) {
      let found = false;
      for (const stage of this.agentStages) {
        if (stage.key === stageKey) {
          stage.status = 'active';
          found = true;
        } else if (!found) {
          stage.status = 'done';
        } else {
          stage.status = 'pending';
        }
      }
    },

    resetAgentStages() {
      this.agentStages.forEach(s => { s.status = 'pending'; });
    },

    markAllStagesDone() {
      this.agentStages.forEach(s => { s.status = 'done'; });
    },

    // ---- Agent 活动 ----
    updateActivity(toolName, data) {
      const a = this.agentActivity;
      a.currentTool = null;
      switch (toolName) {
        case 'search_exemplars':
          if (data.result) {
            a.searchResult = {
              totalFound: data.result.total_found || 0,
              exemplars: data.result.exemplars || [],
            };
          }
          break;
        case 'check_format':
          if (data.result) {
            a.reviewResult = {
              round: a.reviewRound,
              issues: data.result.issues || [],
              criticalCount: data.result.critical_count || 0,
              summary: data.result.summary || '',
            };
          }
          break;
        case 'refine_draft':
          a.refineResult = {
            charCount: data.result
              ? (typeof data.result === 'string' ? data.result.length : (data.result.char_count || 0))
              : 0,
          };
          break;
        default:
          break;
      }
    },

    onToolStart(tool) {
      this.agentActivity.currentTool = tool;
      if (tool === 'search_exemplars') this.setAgentStage('search');
      else if (tool === 'check_format') {
        this.setAgentStage('review');
        this.agentActivity.reviewRound++;
        this.agentActivity.reviewResult = {
          round: this.agentActivity.reviewRound,
          issues: [],
          criticalCount: 0,
          summary: '正在审查...',
        };
      } else if (tool === 'refine_draft') this.setAgentStage('fix');
    },

    onStatusMessage(msg) {
      if (msg.includes('检索')) this.setAgentStage('search');
      else if (msg.includes('初稿') || msg.includes('撰写')) this.setAgentStage('draft');
      else if (msg.includes('审查')) this.setAgentStage('review');
      else if (msg.includes('修复')) this.setAgentStage('fix');
    },

    markDraftReady() {
      this.agentActivity.draftReady = true;
    },
  },
});

/**
 * 从公文正文中提取标题（纯函数，不依赖 store）。
 */
function extractTitle(content) {
  if (!content) return '（未提取到标题）';
  const lines = content.split('\n').filter(l => l.trim());
  for (const line of lines.slice(0, 3)) {
    if (line.includes('关于') && line.length <= 80) return line.trim();
  }
  return (lines[0] || '').slice(0, 60).trim() || '（未提取到标题）';
}
