/**
 * 工具图标、标签映射等全局常量
 */

// 工具图标映射
export const TOOL_ICONS = {
  search_exemplars: '🔍',
  check_format: '✅',
  refine_draft: '🔧',
  ask_user: '❓',
  finish: '🏁',
};

// 工具中文标签
export const TOOL_LABELS = {
  search_exemplars: '检索范文',
  check_format: '格式审查',
  refine_draft: '定向精修',
  ask_user: '询问用户',
  finish: '完成任务',
};

// 文种颜色映射
export const DOC_TYPE_COLORS = {
  '请示': 'blue',
  '报告': 'orange',
  '通知': 'green',
  '函': 'purple',
  '纪要': 'cyan',
  '决定': 'red',
  '通报': 'geekblue',
  '批复': 'lime',
  '公告': 'gold',
  '意见': 'magenta',
};

// Agent 阶段定义
export const AGENT_STAGES = [
  { key: 'analyze', icon: '📋', label: '分析需求' },
  { key: 'search', icon: '🔍', label: '检索范文' },
  { key: 'draft', icon: '✍️', label: '撰写初稿' },
  { key: 'review', icon: '✅', label: '格式审查' },
  { key: 'fix', icon: '🔧', label: '定向修复' },
  { key: 'finish', icon: '🏁', label: '输出终稿' },
];

// 快速模板
export const QUICK_TEMPLATES = [
  { label: '请示', text: '写一份关于申请购买3台服务器的请示', color: 'blue' },
  { label: '通知', text: '写一份关于召开2026年度工作会议的通知', color: 'green' },
  { label: '报告', text: '写一份2025年度工作总结报告', color: 'orange' },
  { label: '函', text: '写一份关于商请开展合作事宜的函', color: 'purple' },
  { label: '纪要', text: '写一份关于项目推进会的会议纪要', color: 'cyan' },
];
