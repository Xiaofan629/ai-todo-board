import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import type { Todo, TodoStatus } from '../types';
import { reorderTodo } from '../api';
import TodoCard from './TodoCard';
import GanttChart from './GanttChart';

interface TodoListProps {
  todos: Todo[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

const STATUS_FILTERS: { value: TodoStatus | 'all' | 'not_done'; label: string }[] = [
  { value: 'not_done', label: '未完成' },
  { value: 'all', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'doing', label: '进行中' },
  { value: 'done', label: '已完成' },
];

const DATE_FILTERS: { value: number; label: string }[] = [
  { value: 7, label: '近7天' },
  { value: 30, label: '近30天' },
  { value: 0, label: '全部' },
];

export default function TodoList({ todos, selectedId, onSelect }: TodoListProps) {
  const [statusFilter, setStatusFilter] = useState<TodoStatus | 'all' | 'not_done'>('not_done');
  const [dateFilter, setDateFilter] = useState(7);
  const [searchQuery, setSearchQuery] = useState('');
  const [ownerName, setOwnerName] = useState('TODOs');
  const [showGanttModal, setShowGanttModal] = useState(false);

  // Drag state
  const [dragSourceId, setDragSourceId] = useState<number | null>(null);
  const [dropIndicator, setDropIndicator] = useState<{ index: number; position: 'top' | 'bottom' } | null>(null);

  // Reason modal
  const [showReasonModal, setShowReasonModal] = useState(false);
  const [reasonText, setReasonText] = useState('');
  const [pendingReorder, setPendingReorder] = useState<{ todoId: number; targetIndex: number; promoteToDoing: boolean } | null>(null);

  // Track the drag target index calculated on last dragOver
  const dropTargetRef = useRef<{ index: number; position: 'top' | 'bottom' } | null>(null);

  useEffect(() => {
    fetch('./api/config')
      .then(res => res.json())
      .then(data => setOwnerName(data.owner_name))
      .catch(() => {});
  }, []);

  const filteredTodos = useMemo(() => {
    let result = todos;

    if (dateFilter > 0) {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - dateFilter);
      result = result.filter((t) => new Date(t.created_at) >= cutoff);
    }

    if (statusFilter === 'not_done') {
      result = result.filter((t) => t.status !== 'done');
    } else if (statusFilter !== 'all') {
      result = result.filter((t) => t.status === statusFilter);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          t.content.toLowerCase().includes(q) ||
          t.userid.toLowerCase().includes(q),
      );
    }

    return result;
  }, [todos, statusFilter, dateFilter, searchQuery]);

  const handleDragStart = useCallback((todoId: number) => {
    setDragSourceId(todoId);
    setDropIndicator(null);
    dropTargetRef.current = null;
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    // Determine top/bottom based on mouse Y relative to the card center
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    const position: 'top' | 'bottom' = e.clientY < midY ? 'top' : 'bottom';

    const newIndicator = { index, position };
    // Only update state if it actually changed
    const prev = dropTargetRef.current;
    if (!prev || prev.index !== newIndicator.index || prev.position !== newIndicator.position) {
      dropTargetRef.current = newIndicator;
      setDropIndicator(newIndicator);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const sourceId = dragSourceId;
    const target = dropTargetRef.current;
    setDropIndicator(null);
    dropTargetRef.current = null;
    setDragSourceId(null);

    if (sourceId === null || !target) return;

    const sourceTodo = filteredTodos.find((t) => t.id === sourceId);
    if (!sourceTodo) return;
    const sourceIndex = filteredTodos.findIndex((t) => t.id === sourceId);

    // Calculate the target position in the filtered array
    let targetIndex = target.position === 'top' ? target.index : target.index + 1;
    // If dragging down, subtract 1 because removing the source shifts everything up
    if (sourceIndex < targetIndex) {
      targetIndex -= 1;
    }
    // Same position, no-op
    if (sourceIndex === targetIndex) return;

    // Determine if this should promote to doing:
    // The drop target is the first doing item, and we're dropping above it (position='top')
    // Or the filtered list has a doing item at index 0, and targetIndex ends up 0
    const firstDoingIndex = filteredTodos.findIndex((t) => t.status === 'doing');
    const dropBeforeDoing = firstDoingIndex !== -1 && targetIndex <= firstDoingIndex;
    const promoteToDoing = sourceTodo.status === 'pending' && dropBeforeDoing;

    setPendingReorder({ todoId: sourceId, targetIndex, promoteToDoing });
    setReasonText('');
    setShowReasonModal(true);
  }, [dragSourceId, filteredTodos]);

  const handleDragEnd = useCallback(() => {
    setDragSourceId(null);
    setDropIndicator(null);
    dropTargetRef.current = null;
  }, []);

  const confirmReorder = async () => {
    if (!pendingReorder) return;
    try {
      await reorderTodo(pendingReorder.todoId, pendingReorder.targetIndex, reasonText, pendingReorder.promoteToDoing);
    } catch (err) {
      console.error('Failed to reorder:', err);
    }
    setShowReasonModal(false);
    setPendingReorder(null);
    setReasonText('');
  };

  const cancelReorder = () => {
    setShowReasonModal(false);
    setPendingReorder(null);
    setReasonText('');
  };

  /** Determine the drop indicator for a given card index. */
  const getDropPosition = (index: number): 'top' | 'bottom' | null => {
    if (!dropIndicator || dragSourceId === null) return null;
    if (dropIndicator.index !== index) return null;

    // Don't show indicator on the source itself at its own position
    const sourceIndex = filteredTodos.findIndex((t) => t.id === dragSourceId);
    if (sourceIndex === index) return null;

    return dropIndicator.position;
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 pt-4 pb-2 flex-shrink-0">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold text-gray-100 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
            </svg>
            {ownerName}的TODOs
          </h1>
          <a
            href="https://github.com/Xiaofan629/ai-todo-board"
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => { e.preventDefault(); window.open('https://github.com/Xiaofan629/ai-todo-board', '_blank'); }}
            className="text-gray-400 hover:text-gray-200 transition-colors"
            title="GitHub"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
            </svg>
          </a>
        </div>
      </div>

      {/* Search + View toggle */}
      <div className="px-4 pb-2 flex-shrink-0 flex items-center gap-2">
        <div className="relative flex-1">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <input
            type="text"
            placeholder="搜索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700/50 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/30 transition-colors"
          />
        </div>
        <button
          type="button"
          onClick={() => setShowGanttModal(true)}
          className="p-2 bg-gray-800 border border-gray-700/50 rounded-lg text-gray-400 hover:text-blue-400 hover:border-blue-500/30 transition-colors"
          title="甘特图"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18v16H3zM7 8h6M7 12h10M7 16h4" />
          </svg>
        </button>
      </div>

      {/* Date filter */}
      <div className="px-4 pb-2 flex-shrink-0">
        <div className="flex gap-1 overflow-x-auto scrollbar-thin pb-1">
          {DATE_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setDateFilter(f.value)}
              className={`
                px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-colors
                ${
                  dateFilter === f.value
                    ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-transparent'
                }
              `}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="px-4 pb-2 flex-shrink-0">
        <div className="flex gap-1 overflow-x-auto scrollbar-thin pb-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setStatusFilter(f.value)}
              className={`
                px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-colors
                ${
                  statusFilter === f.value
                    ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800 border border-transparent'
                }
              `}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Todo count */}
      <div className="px-4 pb-2 flex-shrink-0">
        <span className="text-xs text-gray-500">
          {filteredTodos.length} 项
          {statusFilter === 'pending' && ' · 拖拽可排序'}
        </span>
      </div>

      {/* Todo list */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 scrollbar-thin space-y-2">
        {filteredTodos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <svg className="w-12 h-12 mb-3 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 13.875l2.25-2.25M12 13.875l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
            </svg>
            <p className="text-sm">没有找到 TODO</p>
            {searchQuery && (
              <p className="text-xs mt-1">试试其他搜索词</p>
            )}
          </div>
        ) : (
          filteredTodos.map((todo, index) => (
            <TodoCard
              key={todo.id}
              todo={todo}
              index={index}
              isSelected={todo.id === selectedId}
              onClick={() => onSelect(todo.id)}
              draggable={todo.status === 'pending'}
              isDragging={dragSourceId === todo.id}
              dropPosition={getDropPosition(index)}
              onDragStart={() => handleDragStart(todo.id)}
              onDragOver={(e) => handleDragOver(e, index)}
              onDrop={(e) => handleDrop(e)}
              onDragEnd={handleDragEnd}
            />
          ))
        )}
      </div>

      {/* Gantt Chart Modal */}
      {showGanttModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-[90vw] max-w-4xl h-[80vh] flex flex-col overflow-hidden">
            {/* Modal header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800 flex-shrink-0">
              <h2 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18v16H3zM7 8h6M7 12h10M7 16h4" />
                </svg>
                甘特图 · {DATE_FILTERS.find(f => f.value === dateFilter)?.label || '全部'}
              </h2>
              <button
                type="button"
                onClick={() => setShowGanttModal(false)}
                className="p-1.5 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            {/* Modal body */}
            <div className="flex-1 overflow-hidden">
              <GanttChart todos={filteredTodos} onSelect={onSelect} selectedId={selectedId} />
            </div>
          </div>
        </div>
      )}

      {/* Reason Modal */}
      {showReasonModal && (
        <div className="absolute inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 w-full max-w-sm shadow-2xl">
            <h3 className="text-sm font-semibold text-gray-100 mb-3">
              移动排序
            </h3>
            <p className="text-xs text-gray-400 mb-3">
              可选：填写移动原因
            </p>
            <textarea
              value={reasonText}
              onChange={(e) => setReasonText(e.target.value)}
              placeholder="移动原因（可不填）"
              rows={3}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500/50 resize-none"
            />
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                onClick={cancelReorder}
                className="flex-1 px-3 py-2 text-sm text-gray-400 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmReorder}
                className="flex-1 px-3 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
