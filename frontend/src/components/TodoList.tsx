import { useState, useMemo, useEffect } from 'react';
import type { Todo, TodoStatus } from '../types';
import TodoCard from './TodoCard';

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

  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(data => setOwnerName(data.owner_name))
      .catch(() => {});
  }, []);

  const filteredTodos = useMemo(() => {
    let result = todos;

    // Filter by date
    if (dateFilter > 0) {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - dateFilter);
      result = result.filter((t) => new Date(t.created_at) >= cutoff);
    }

    // Filter by status
    if (statusFilter === 'not_done') {
      result = result.filter((t) => t.status !== 'done');
    } else if (statusFilter !== 'all') {
      result = result.filter((t) => t.status === statusFilter);
    }

    // Filter by search query
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

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 pt-4 pb-2 flex-shrink-0">
        <h1 className="text-lg font-bold text-gray-100 flex items-center gap-2">
          <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
          </svg>
          {ownerName}的TODOs
        </h1>
      </div>

      {/* Search */}
      <div className="px-4 pb-2 flex-shrink-0">
        <div className="relative">
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
          filteredTodos.map((todo) => (
            <TodoCard
              key={todo.id}
              todo={todo}
              isSelected={todo.id === selectedId}
              onClick={() => onSelect(todo.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
