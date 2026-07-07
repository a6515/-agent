/**
 * 后端 API 调用封装
 */

const AI_API_BASE = process.env.VUE_APP_API_BASE || '';

/**
 * 快速模式 SSE 流式生成
 */
export function generateQuickStream(prompt, signal) {
  return fetch(`${AI_API_BASE}/generate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, retrieve_k: 4, temperature: 0.3 }),
    signal,
  });
}

/**
 * 深度模式 Agent SSE 流式生成
 */
export function generateAgentStream({ prompt, history, currentDraft }, signal) {
  return fetch(`${AI_API_BASE}/generate/agent/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt,
      retrieve_k: 4,
      temperature: 0.3,
      messages: history,
      current_draft: currentDraft,
    }),
    signal,
  });
}

/**
 * 向等待中的 Agent 注入用户回答
 */
export function submitAgentAnswer(sessionId, answer) {
  return fetch(`${AI_API_BASE}/generate/agent/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer }),
  });
}

/**
 * 下载 .docx 文件 URL（同源下载按钮用，相对/AI_API_BASE 皆可）
 */
export function getDownloadUrl(filename) {
  return `${AI_API_BASE}/download/${encodeURIComponent(filename)}`;
}

/**
 * 下载 .docx 的**绝对** URL —— 用于 postMessage 发给非同源的 OA 父窗口。
 *
 * OA 发文页面与 AI 前端不同源，收到的 URL 必须带 host 才能下载；且下载端点在
 * AI 后端（8000），不能用 AI 前端自身的 origin（开发模式是 8081，会 404）。
 *  - 开发模式：VUE_APP_API_BASE=http://localhost:8000（绝对）→ 直接用
 *  - 生产模式：VUE_APP_API_BASE 为空（前后端同源）→ 用当前页面 origin
 */
export function getAbsoluteDownloadUrl(filename) {
  const base = /^https?:\/\//i.test(AI_API_BASE) ? AI_API_BASE : window.location.origin;
  return `${base}/download/${encodeURIComponent(filename)}`;
}
