/**
 * SSE (Server-Sent Events) 流解析工具
 *
 * 用法：
 *   const events = await readSSEStream(response, (ev) => console.log(ev));
 *
 * 兼容标准 SSE 协议：event: xxx\ndata: {...}\n\n
 */

/**
 * 流式读取 SSE 响应体，实时回调每个事件。
 *
 * @param {Response} response - fetch() 返回的 Response 对象
 * @param {(ev: {event: string, data: any}) => void} [onEvent] - 可选实时回调
 * @returns {Promise<Array<{event: string, data: any}>>} 所有事件的数组
 */
export async function readSSEStream(response, onEvent = null) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const events = [];
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    buffer += chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    const parts = buffer.split('\n\n');
    buffer = parts.pop();

    for (const part of parts) {
      if (!part.trim()) continue;
      const ev = parseSSEEvent(part);
      if (ev) {
        events.push(ev);
        if (onEvent) {
          try {
            onEvent(ev);
          } catch (e) {
            console.error('SSE onEvent error:', e);
          }
        }
      }
    }
  }

  if (buffer.trim()) {
    const ev = parseSSEEvent(buffer);
    if (ev) {
      events.push(ev);
      if (onEvent) {
        try {
          onEvent(ev);
        } catch (e) {
          console.error('SSE onEvent error:', e);
        }
      }
    }
  }

  return events;
}

/**
 * 解析单条 SSE 原始文本为结构化对象。
 *
 * @param {string} raw - 单条 SSE 文本
 * @returns {{event: string, data: any}}
 */
export function parseSSEEvent(raw) {
  const event = { event: 'message', data: {} };
  const normalized = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines = normalized.split('\n');

  for (const line of lines) {
    if (line.startsWith('event: ')) {
      event.event = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      try {
        event.data = JSON.parse(line.slice(6));
      } catch (_) {
        event.data = line.slice(6);
      }
    }
  }

  // 容错：某些 SSE 实现把 event 放在 data JSON 内
  if (
    event.event === 'message' &&
    event.data &&
    typeof event.data === 'object' &&
    event.data.event
  ) {
    event.event = event.data.event;
  }

  return event;
}
