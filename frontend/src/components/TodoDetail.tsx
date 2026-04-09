import { useState, useRef, useEffect, useCallback } from 'react';
import type { Todo, Message } from '../types';
import { fetchMessages, sendChat, completeTodo, completeTodoFromPending, deleteTodo, updateTodoTitle } from '../api';
import MessageBubble from './MessageBubble';

interface TodoDetailProps {
  todo: Todo;
  onBack: () => void;
  onDeleted?: () => void;
  onTitleChanged?: () => void;
}

export default function TodoDetail({ todo, onBack, onDeleted, onTitleChanged }: TodoDetailProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [showScrollTopBtn, setShowScrollTopBtn] = useState(false);
  const [modelName, setModelName] = useState('AI');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editTitleText, setEditTitleText] = useState('');
  const titleInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('./api/config')
      .then(res => res.json())
      .then(data => setModelName(data.llm_model || 'AI'))
      .catch(() => {});
  }, []);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const remoteProcessing = todo.is_processing;
  const inputDisabled = sending || remoteProcessing || todo.status === 'done';

  const scrollToBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  const scrollToTop = useCallback(() => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, []);

  const checkScrollPosition = useCallback(() => {
    const el = scrollContainerRef.current;
    if (el) {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      setShowScrollBtn(!nearBottom);
      setShowScrollTopBtn(el.scrollTop > 400);
    }
  }, []);

  const loadMessages = useCallback(async () => {
    if (!todo) return;
    try {
      setLoading(true);
      setError(null);
      const msgs = await fetchMessages(todo.id);
      setMessages(msgs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load messages');
    } finally {
      setLoading(false);
    }
  }, [todo]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  useEffect(() => {
    if (!remoteProcessing) return;
    const timer = window.setInterval(() => {
      void loadMessages();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [remoteProcessing, loadMessages]);

  useEffect(() => {
    if (messages.length > 0) {
      scrollToBottom();
    }
  }, [messages.length, scrollToBottom]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (el) {
      el.addEventListener('scroll', checkScrollPosition);
      return () => el.removeEventListener('scroll', checkScrollPosition);
    }
  }, [checkScrollPosition]);

  const handleSend = useCallback(async () => {
    const text = inputText.trim();
    if (!text || inputDisabled) return;

    setSending(true);
    setInputText('');

    try {
      await sendChat(todo.id, text);
      const msgs = await fetchMessages(todo.id);
      setMessages(msgs);
      setTimeout(scrollToBottom, 100);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [inputDisabled, inputText, todo.id, scrollToBottom]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleComplete = useCallback(async () => {
    if (!todo || todo.status === 'done') return;
    try {
      if (todo.status === 'pending') {
        await completeTodoFromPending(todo.id);
      } else {
        await completeTodo(todo.id);
      }
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : '完成操作失败');
    }
  }, [todo, loadMessages]);

  const handleDelete = useCallback(async () => {
    if (!todo) return;
    try {
      await deleteTodo(todo.id);
      setShowDeleteConfirm(false);
      onDeleted?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
      setShowDeleteConfirm(false);
    }
  }, [todo, onDeleted]);

  const statusConfig: Record<string, { color: string; label: string }> = {
    pending: { color: 'bg-yellow-400/20 text-yellow-300 border-yellow-500/30', label: '待处理' },
    doing: { color: 'bg-blue-400/20 text-blue-300 border-blue-500/30', label: '进行中' },
    done: { color: 'bg-emerald-400/20 text-emerald-300 border-emerald-500/30', label: '已完成' },
  };

  const sc = statusConfig[todo.status];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm">
        <div className="flex items-center gap-2 px-4 py-2">
          <button
            type="button"
            onClick={onBack}
            className="lg:hidden p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
            </svg>
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              {editingTitle ? (
                <input
                  ref={titleInputRef}
                  value={editTitleText}
                  onChange={(e) => setEditTitleText(e.target.value)}
                  onBlur={async () => {
                    const trimmed = editTitleText.trim();
                    if (trimmed && trimmed !== todo.title) {
                      await updateTodoTitle(todo.id, trimmed);
                      onTitleChanged?.();
                    }
                    setEditingTitle(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') titleInputRef.current?.blur();
                    if (e.key === 'Escape') { setEditingTitle(false); setEditTitleText(''); }
                  }}
                  className="text-base font-semibold text-gray-100 bg-gray-800 border border-blue-500/50 rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-blue-500/30 w-full"
                  autoFocus
                />
              ) : (
                <h2
                  className="text-base font-semibold text-gray-100 truncate cursor-pointer hover:text-blue-300 transition-colors group flex items-center gap-1"
                  onClick={() => { setEditTitleText(todo.title || ''); setEditingTitle(true); }}
                  title="点击编辑标题"
                >
                  {todo.title || `Todo #${todo.id}`}
                  <svg className="w-3.5 h-3.5 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                  </svg>
                </h2>
              )}
              {sc && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${sc.color}`}>
                  {sc.label}
                </span>
              )}
            </div>
            {todo.userid && (
              <p className="text-xs text-gray-500 mt-0.5">来自: {todo.userid}</p>
            )}
          </div>

          {(todo.status === 'doing' || todo.status === 'pending') && (
            <button
              type="button"
              onClick={handleComplete}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors"
            >
              标记完成
            </button>
          )}

          <button
            type="button"
            onClick={loadMessages}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
            title="刷新消息"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
            </svg>
          </button>

          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-600 hover:text-red-400 transition-colors"
            title="删除"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
          </button>
        </div>
      </div>

      {/* Messages area */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 py-4 scrollbar-thin relative">
        {loading && messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="flex items-center gap-2 text-gray-400">
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-sm">加载中...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-900/30 border border-red-700/50 text-red-300 text-sm">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span>{error}</span>
            </div>
          </div>
        )}

        {!loading && messages.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <svg className="w-12 h-12 mb-3 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
            </svg>
            <p className="text-sm">暂无消息</p>
            <p className="text-xs mt-1">在下方开始对话</p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {sending && (
          <div className="animate-fade-in mb-3 flex justify-start">
            <div className="flex items-center gap-2 bg-gray-800 border border-gray-700/50 rounded-2xl rounded-bl-md px-4 py-2.5">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-xs text-gray-400">思考中...</span>
            </div>
          </div>
        )}

        {remoteProcessing && !sending && (
          <div className="animate-fade-in mb-3 flex justify-start">
            <div className="flex items-center gap-2 bg-gray-800 border border-blue-700/40 rounded-2xl rounded-bl-md px-4 py-2.5">
              <svg className="w-4 h-4 animate-spin text-blue-300" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-xs text-blue-200">{modelName} 正在处理中，请稍候...</span>
            </div>
          </div>
        )}

        {showScrollBtn && (
          <button
            type="button"
            onClick={scrollToBottom}
            className="sticky bottom-2 left-1/2 -translate-x-1/2 flex items-center justify-center w-9 h-9 rounded-full bg-gray-700/90 border border-gray-600/50 text-gray-300 hover:bg-gray-600 hover:text-white shadow-lg transition-all animate-fade-in"
            title="滚动到底部"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
            </svg>
          </button>
        )}

        {showScrollTopBtn && (
          <button
            type="button"
            onClick={scrollToTop}
            className="sticky top-2 left-1/2 -translate-x-1/2 flex items-center justify-center w-9 h-9 rounded-full bg-gray-700/90 border border-gray-600/50 text-gray-300 hover:bg-gray-600 hover:text-white shadow-lg transition-all animate-fade-in"
            title="回到顶部"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
            </svg>
          </button>
        )}
      </div>

      {/* Chat input */}
      <div className="flex-shrink-0 border-t border-gray-700/50 bg-gray-900/80 backdrop-blur-sm p-3">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                remoteProcessing
                  ? `${modelName} 正在处理中，请稍候...`
                  : sending
                    ? '等待回复...'
                    : todo.status === 'done'
                      ? '该会话已完成，无法继续发送消息'
                      : '输入消息... (Shift+Enter 发送)'
              }
              disabled={inputDisabled}
              rows={1}
              className="w-full resize-none rounded-xl bg-gray-800 border border-gray-700/50 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ maxHeight: '120px', minHeight: '40px', height: 'auto' }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = 'auto';
                target.style.height = `${Math.min(target.scrollHeight, 120)}px`;
              }}
            />
          </div>
          <button
            type="button"
            onClick={handleSend}
            disabled={!inputText.trim() || inputDisabled}
            className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-xl bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-blue-600"
          >
            {sending ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Delete confirmation */}
      {showDeleteConfirm && (
        <div className="absolute inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 w-full max-w-sm shadow-2xl">
            <h3 className="text-sm font-semibold text-gray-100 mb-2">确认删除</h3>
            <p className="text-xs text-gray-400 mb-4">
              删除后无法恢复，该 Todo 及其所有消息将被永久删除。
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 px-3 py-2 text-sm text-gray-400 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleDelete}
                className="flex-1 px-3 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-500 transition-colors"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
