import type { Message } from '../types';

type JsonRecord = Record<string, unknown>;

interface MessageBubbleProps {
  message: Message;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function tryPrettyJson(raw: string): string {
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return raw;
  }
}

function parsePayload(raw: string): JsonRecord | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as JsonRecord;
    }
  } catch {
    return null;
  }
  return null;
}

function stringifyValue(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return tryPrettyJson(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function extractText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (!Array.isArray(value)) return '';

  const parts = value.flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const block = item as JsonRecord;
    const type = typeof block.type === 'string' ? block.type : '';
    if (type === 'text') {
      return typeof block.text === 'string' ? [block.text] : [];
    }
    if (type === 'thinking') {
      return typeof block.thinking === 'string' ? [block.thinking] : [];
    }
    if (type === 'tool_result') {
      return [extractText(block.content)];
    }
    if (type === 'compaction') {
      return typeof block.content === 'string' ? [block.content] : [];
    }
    return [];
  });

  return parts.filter(Boolean).join('\n').trim();
}

function getMessageRole(payload: JsonRecord | null, fallbackRole: Message['role']): Message['role'] {
  const payloadRole = payload?.message;
  if (payloadRole && typeof payloadRole === 'object' && !Array.isArray(payloadRole)) {
    const role = (payloadRole as JsonRecord).role;
    if (role === 'user' || role === 'assistant') {
      return role;
    }
  }
  return fallbackRole;
}

function getContentBlocks(payload: JsonRecord | null): JsonRecord[] {
  const message = payload?.message;
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    return [];
  }
  const content = (message as JsonRecord).content;
  if (!Array.isArray(content)) return [];
  return content.filter(
    (item): item is JsonRecord => !!item && typeof item === 'object' && !Array.isArray(item),
  );
}

function blockLabel(type: string): string {
  switch (type) {
    case 'tool_use':
    case 'server_tool_use':
    case 'mcp_tool_use':
      return 'Tool Use';
    case 'tool_result':
    case 'web_search_tool_result':
    case 'web_fetch_tool_result':
    case 'code_execution_tool_result':
    case 'bash_code_execution_tool_result':
    case 'text_editor_code_execution_tool_result':
    case 'mcp_tool_result':
    case 'tool_search_tool_result':
      return 'Tool Result';
    case 'thinking':
      return 'Thinking';
    case 'compaction':
      return 'Compaction';
    default:
      return type || 'Block';
  }
}

function blockTitle(block: JsonRecord): string {
  const type = typeof block.type === 'string' ? block.type : '';
  if (type === 'tool_use' || type === 'server_tool_use' || type === 'mcp_tool_use') {
    return typeof block.name === 'string' ? block.name : blockLabel(type);
  }
  if (type === 'tool_result') {
    return typeof block.tool_use_id === 'string' ? `tool_result:${block.tool_use_id}` : 'Tool Result';
  }
  return blockLabel(type);
}

function blockBody(block: JsonRecord): string {
  const type = typeof block.type === 'string' ? block.type : '';
  if (type === 'text') {
    return typeof block.text === 'string' ? block.text : '';
  }
  if (type === 'thinking') {
    return typeof block.thinking === 'string' ? block.thinking : '';
  }
  if (type === 'tool_use' || type === 'server_tool_use' || type === 'mcp_tool_use') {
    return stringifyValue(block.input ?? {});
  }
  if ('content' in block) {
    const nestedText = extractText(block.content);
    return nestedText || stringifyValue(block.content);
  }
  return stringifyValue(block);
}

function renderLegacyToolMessage(message: Message) {
  const preview = message.tool_input
    ? (() => {
        try {
          const parsed = JSON.parse(message.tool_input);
          const keys = Object.keys(parsed);
          return keys.length > 0 ? keys.slice(0, 3).join(', ') : '';
        } catch {
          return message.tool_input.substring(0, 40);
        }
      })()
    : '';

  return (
    <div className="animate-fade-in mb-3">
      <details className="group rounded-lg border border-gray-700/50 bg-gray-800/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-left">
          <span className="text-sm font-semibold text-amber-300">
            {message.tool_name || 'Tool Call'}
          </span>
          {preview && (
            <span className="truncate text-xs text-gray-500">{preview}</span>
          )}
          <span className="ml-auto text-xs text-gray-500">{formatTime(message.created_at)}</span>
        </summary>
        <div className="space-y-2 border-t border-gray-700/50 px-3 py-3">
          {(message.tool_input || message.tool_name) && (
            <div>
              <div className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
                参数
              </div>
              <pre className="tool-json max-h-[400px] overflow-y-auto scrollbar-thin">
                {tryPrettyJson(message.tool_input || '')}
              </pre>
            </div>
          )}
          {message.content && (
            <div>
              <div className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
                返回结果
              </div>
              <pre className="tool-json max-h-[400px] overflow-y-auto scrollbar-thin">
                {tryPrettyJson(message.content)}
              </pre>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

function renderSystemEvent(message: Message, payload: JsonRecord | null) {
  const type = message.event_type || (typeof payload?.type === 'string' ? payload.type : 'system');
  const subtype =
    message.event_subtype || (typeof payload?.subtype === 'string' ? payload.subtype : '');
  const summary =
    message.content ||
    (type === 'result'
      ? subtype === 'success'
        ? 'Claude Code 已完成'
        : 'Claude Code 执行结束'
      : type === 'error'
      ? (typeof payload?.message === 'string' ? payload.message : 'Claude Code 错误')
      : subtype || type);

  return (
    <div className="animate-fade-in mb-3">
      <details className="rounded-lg border border-gray-800 bg-gray-900/70">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-left">
          <span className="rounded border border-gray-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-gray-400">
            {subtype || type}
          </span>
          <span className="truncate text-sm text-gray-300">{summary || 'System Event'}</span>
          <span className="ml-auto text-xs text-gray-500">{formatTime(message.created_at)}</span>
        </summary>
        {payload && (
          <div className="border-t border-gray-800 px-3 py-3">
            <pre className="tool-json max-h-[320px] overflow-y-auto scrollbar-thin">
              {JSON.stringify(payload, null, 2)}
            </pre>
          </div>
        )}
      </details>
    </div>
  );
}

function renderClaudeBlocks(blocks: JsonRecord[]) {
  const specialBlocks = blocks.filter((block) => {
    const type = typeof block.type === 'string' ? block.type : '';
    return type !== 'text';
  });

  if (specialBlocks.length === 0) return null;

  return (
    <div className="mt-2 space-y-2">
      {specialBlocks.map((block, index) => {
        const type = typeof block.type === 'string' ? block.type : '';
        const body = blockBody(block);
        return (
          <details
            key={`${type}-${index}`}
            className="rounded-xl border border-gray-700/50 bg-gray-900/70"
          >
            <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-left">
              <span className="rounded border border-gray-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-gray-400">
                {blockLabel(type)}
              </span>
              <span className="truncate text-sm text-gray-200">{blockTitle(block)}</span>
            </summary>
            <div className="border-t border-gray-700/50 px-3 py-3">
              <pre className="tool-json max-h-[360px] overflow-y-auto scrollbar-thin">
                {body || stringifyValue(block)}
              </pre>
            </div>
          </details>
        );
      })}
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === 'tool' && !message.payload && !message.event_type) {
    return renderLegacyToolMessage(message);
  }

  const payload = parsePayload(message.payload);
  const eventType = message.event_type || (typeof payload?.type === 'string' ? payload.type : '');
  const blocks = getContentBlocks(payload);
  const payloadRole = getMessageRole(payload, message.role);
  const textContent = blocks.length > 0 ? extractText(blocks) : message.content;

  if (message.role === 'system' || eventType === 'system' || eventType === 'result' || eventType === 'error') {
    return renderSystemEvent(message, payload);
  }

  if (payloadRole === 'user' && blocks.length > 0 && blocks.every((block) => block.type === 'text')) {
    return (
      <div className="animate-fade-in mb-3 flex justify-end">
        <div className="max-w-[80%] lg:max-w-[70%]">
          <div className="rounded-2xl rounded-br-md bg-blue-600/80 px-4 py-2.5 text-sm leading-relaxed text-white whitespace-pre-wrap break-words">
            {textContent}
          </div>
          <div className="mt-1 text-right text-xs text-gray-500">{formatTime(message.created_at)}</div>
        </div>
      </div>
    );
  }

  if (payloadRole === 'assistant' && blocks.length > 0 && blocks.every((block) => block.type === 'text')) {
    return (
      <div className="animate-fade-in mb-3 flex justify-start">
        <div className="max-w-[80%] lg:max-w-[70%]">
          <div className="flex items-start gap-2">
            <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-emerald-500/40 bg-emerald-600/30">
              <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <div className="rounded-2xl rounded-bl-md border border-gray-700/50 bg-gray-800 px-4 py-2.5 text-sm leading-relaxed text-gray-100 whitespace-pre-wrap break-words">
                {textContent}
              </div>
              <div className="mt-1 text-xs text-gray-500">{formatTime(message.created_at)}</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (blocks.length > 0) {
    return (
      <div className="animate-fade-in mb-4 space-y-2">
        {textContent && (
          <div className="flex justify-start">
            <div className="max-w-[88%] rounded-2xl border border-gray-700/50 bg-gray-800 px-4 py-2.5 text-sm leading-relaxed text-gray-100 whitespace-pre-wrap break-words">
              {textContent}
            </div>
          </div>
        )}
        {renderClaudeBlocks(blocks)}
        <div className="text-xs text-gray-500">{formatTime(message.created_at)}</div>
      </div>
    );
  }

  if (message.role === 'user') {
    return (
      <div className="animate-fade-in mb-3 flex justify-end">
        <div className="max-w-[80%] lg:max-w-[70%]">
          <div className="rounded-2xl rounded-br-md bg-blue-600/80 px-4 py-2.5 text-sm leading-relaxed text-white whitespace-pre-wrap break-words">
            {message.content}
          </div>
          <div className="mt-1 text-right text-xs text-gray-500">{formatTime(message.created_at)}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in mb-3 flex justify-start">
      <div className="max-w-[80%] lg:max-w-[70%]">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-emerald-500/40 bg-emerald-600/30">
            <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <div className="rounded-2xl rounded-bl-md border border-gray-700/50 bg-gray-800 px-4 py-2.5 text-sm leading-relaxed text-gray-100 whitespace-pre-wrap break-words">
              {message.content}
            </div>
            <div className="mt-1 text-xs text-gray-500">{formatTime(message.created_at)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
