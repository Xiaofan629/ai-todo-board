import { useState, useEffect, useCallback, useRef } from 'react';
import type { Todo, Stats } from './types';
import { fetchTodos, fetchStats } from './api';
import TodoList from './components/TodoList';
import TodoDetail from './components/TodoDetail';

const POLL_INTERVAL = 2000; // 2 seconds

export default function App() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showDetail, setShowDetail] = useState(false); // for mobile
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Fetch all data (todos + stats). */
  const refreshData = useCallback(async () => {
    try {
      const [todosData, statsData] = await Promise.all([
        fetchTodos(),
        fetchStats(),
      ]);
      setTodos(todosData);
      setStats(statsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + polling
  useEffect(() => {
    refreshData();
    pollingRef.current = setInterval(refreshData, POLL_INTERVAL);
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [refreshData]);

  /** Handle todo selection. */
  const handleSelectTodo = useCallback((id: number) => {
    setSelectedId(id);
    setShowDetail(true);
  }, []);

  /** Handle back from detail (mobile). */
  const handleBack = useCallback(() => {
    setShowDetail(false);
  }, []);

  const selectedTodo = selectedId ? todos.find((t) => t.id === selectedId) ?? null : null;

  // --- Loading state ---
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <svg className="w-8 h-8 animate-spin text-blue-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm text-gray-400">加载中...</span>
        </div>
      </div>
    );
  }

  // --- Connection error state ---
  if (error && todos.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-900">
        <div className="flex flex-col items-center gap-3 max-w-sm text-center px-4">
          <svg className="w-12 h-12 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <h2 className="text-lg font-semibold text-gray-100">连接错误</h2>
          <p className="text-sm text-gray-400">{error}</p>
          <button
            type="button"
            onClick={refreshData}
            className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-900">
      {/* Stats bar */}
      {stats && (
        <div className="flex-shrink-0 border-b border-gray-800 bg-gray-900/90 backdrop-blur-sm">
          <div className="flex items-center gap-4 px-4 py-2 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-yellow-400" />
              <span className="text-gray-400">待处理:</span>
              <span className="text-yellow-300 font-medium">{stats.pending ?? 0}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse-dot" />
              <span className="text-gray-400">进行中:</span>
              <span className="text-blue-300 font-medium">{stats.doing ?? 0}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-gray-400">已完成:</span>
              <span className="text-emerald-300 font-medium">{stats.done ?? 0}</span>
            </span>
            <span className="ml-auto text-gray-600">
              自动刷新: 2s
            </span>
          </div>
        </div>
      )}

      {/* Main content: left-right split */}
      <div className="flex-1 flex min-h-0">
        {/* Left panel - Todo List */}
        <div
          className={`
            flex-shrink-0 border-r border-gray-800 bg-gray-900
            w-full lg:w-80 xl:w-96
            ${showDetail ? 'hidden lg:flex lg:flex-col' : 'flex flex-col'}
          `}
        >
          <TodoList
            todos={todos}
            selectedId={selectedId}
            onSelect={handleSelectTodo}
          />
        </div>

        {/* Right panel - Todo Detail */}
        <div
          className={`
            flex-1 min-w-0 bg-gray-900
            ${showDetail ? 'flex flex-col' : 'hidden lg:flex lg:flex-col'}
          `}
        >
          {selectedTodo ? (
            <TodoDetail
              key={selectedTodo.id}
              todo={selectedTodo}
              onBack={handleBack}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center px-4">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
                </svg>
                <h3 className="text-lg font-medium text-gray-400 mb-1">
                  选择一个 TODO
                </h3>
                <p className="text-sm text-gray-500">
                  从列表中选择以查看对话记录
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
