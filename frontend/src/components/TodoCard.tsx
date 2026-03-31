import type { Todo, TodoStatus } from '../types';

interface TodoCardProps {
  todo: Todo;
  isSelected: boolean;
  onClick: () => void;
}

/** Status config: color classes and display labels. */
const STATUS_CONFIG: Record<TodoStatus, { dot: string; bg: string; border: string; label: string }> = {
  pending: {
    dot: 'bg-yellow-400',
    bg: 'bg-yellow-400/10',
    border: 'border-yellow-500/30',
    label: '待处理',
  },
  doing: {
    dot: 'bg-blue-400 animate-pulse-dot',
    bg: 'bg-blue-400/10',
    border: 'border-blue-500/30',
    label: '进行中',
  },
  done: {
    dot: 'bg-emerald-400',
    bg: 'bg-emerald-400/10',
    border: 'border-emerald-500/30',
    label: '已完成',
  },
};

/** Format ISO date to a short readable form. */
function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();

    if (isToday) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function TodoCard({ todo, isSelected, onClick }: TodoCardProps) {
  const cfg = STATUS_CONFIG[todo.status] ?? STATUS_CONFIG.pending;

  const ringColor = todo.status === 'pending'
    ? 'ring-yellow-400'
    : todo.status === 'doing'
    ? 'ring-blue-400'
    : 'ring-emerald-400';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        w-full text-left p-3 rounded-xl border transition-all duration-150 group
        ${
          isSelected
            ? `${cfg.bg} ${cfg.border} ring-1 ring-opacity-40 ${ringColor}`
            : 'bg-gray-800/50 border-gray-700/40 hover:bg-gray-800 hover:border-gray-600/60'
        }
      `}
    >
      {/* Header row: title + status */}
      <div className="flex items-start gap-2">
        {/* Status dot */}
        <span
          className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`}
          title={cfg.label}
        />
        <div className="flex-1 min-w-0">
          {/* Title */}
          <div className="text-sm font-medium text-gray-100 truncate">
            {todo.title || `Todo #${todo.id}`}
          </div>
          {/* Content preview */}
          <div className="text-xs text-gray-400 mt-0.5 line-clamp-2 leading-relaxed">
            {todo.content}
          </div>
        </div>
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between mt-2 ml-4">
        <span className="text-[10px] text-gray-500">
          {formatDate(todo.created_at)}
        </span>
        <span
          className={`
            text-[10px] px-1.5 py-0.5 rounded-full font-medium uppercase tracking-wide
            ${cfg.bg} ${cfg.border} border
          `}
        >
          {cfg.label}
        </span>
      </div>
    </button>
  );
}
