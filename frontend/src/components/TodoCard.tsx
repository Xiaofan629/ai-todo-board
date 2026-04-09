import type { Todo, TodoStatus } from '../types';

interface TodoCardProps {
  todo: Todo;
  index: number;
  isSelected: boolean;
  onClick: () => void;
  onStartDoing?: (todoId: number) => void;
  draggable?: boolean;
  /** 'top' = insertion line above, 'bottom' = line below, null = none */
  dropPosition?: 'top' | 'bottom' | null;
  isDragging?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  onDragEnd?: () => void;
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

export default function TodoCard({
  todo,
  index,
  isSelected,
  onClick,
  onStartDoing,
  draggable,
  dropPosition,
  isDragging,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: TodoCardProps) {
  const cfg = STATUS_CONFIG[todo.status] ?? STATUS_CONFIG.pending;

  const ringColor =
    todo.status === 'pending'
      ? 'ring-yellow-400'
      : todo.status === 'doing'
        ? 'ring-blue-400'
        : 'ring-emerald-400';

  return (
    <div className="relative">
      {/* Insertion line - TOP */}
      {dropPosition === 'top' && (
        <div className="absolute -top-[5px] left-2 right-2 z-10 flex items-center">
          <div className="flex-1 h-[3px] rounded-full bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.6)]" />
          <div className="absolute left-0 w-2 h-2 rounded-full bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]" />
          <div className="absolute right-0 w-2 h-2 rounded-full bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]" />
        </div>
      )}

      <button
        type="button"
        onClick={onClick}
        draggable={draggable}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onDragEnd={onDragEnd}
        className={`
          w-full text-left p-3 rounded-xl border transition-all duration-200 group
          ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}
          ${isDragging ? 'opacity-30 scale-[0.98]' : ''}
          ${
            isSelected
              ? `${cfg.bg} ${cfg.border} ring-1 ring-opacity-40 ${ringColor}`
              : 'bg-gray-800/50 border-gray-700/40 hover:bg-gray-800 hover:border-gray-600/60'
          }
        `}
      >
        {/* Header row: index + title + sender */}
        <div className="flex items-start gap-2">
          {/* Index number */}
          <span className="mt-0.5 text-xs font-mono text-gray-500 w-5 text-right flex-shrink-0 select-none">
            {index + 1}.
          </span>
          <div className="flex-1 min-w-0">
            {/* Title + sender */}
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-100 truncate">
                {todo.title || `Todo #${todo.id}`}
              </span>
              {todo.userid && (
                <span className="flex-shrink-0 text-[10px] text-gray-500">
                  {todo.userid}
                </span>
              )}
            </div>
            {/* Content preview */}
            <div className="text-xs text-gray-400 mt-0.5 line-clamp-2 leading-relaxed">
              {todo.content}
            </div>
          </div>
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between mt-2 ml-7">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-gray-500">
              {formatDate(todo.created_at)}
            </span>
            {todo.reorder_reason && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-500/15 text-orange-300 border border-orange-500/25 truncate max-w-[120px]"
                title={todo.reorder_reason}
              >
                {todo.reorder_reason}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {todo.status === 'pending' && onStartDoing && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onStartDoing(todo.id); }}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-blue-600/20 text-blue-300 border border-blue-500/30 hover:bg-blue-600/40"
              >
                开始处理
              </button>
            )}
            <span
              className={`
                text-[10px] px-1.5 py-0.5 rounded-full font-medium uppercase tracking-wide
                ${cfg.bg} ${cfg.border} border
              `}
            >
              {cfg.label}
            </span>
          </div>
        </div>
      </button>

      {/* Insertion line - BOTTOM */}
      {dropPosition === 'bottom' && (
        <div className="absolute -bottom-[5px] left-2 right-2 z-10 flex items-center">
          <div className="flex-1 h-[3px] rounded-full bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.6)]" />
          <div className="absolute left-0 w-2 h-2 rounded-full bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]" />
          <div className="absolute right-0 w-2 h-2 rounded-full bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]" />
        </div>
      )}
    </div>
  );
}
