import { useMemo, useState, useRef, useCallback, useEffect } from 'react';
import type { Todo, TodoStatus } from '../types';
import { fetchAllTimeSegments } from '../api';
import type { TimeSegment } from '../types';

interface GanttChartProps {
  todos: Todo[];
  onSelect: (id: number) => void;
  selectedId: number | null;
}

interface GanttSegment {
  startTime: number;
  endTime: number;
}

interface GanttBarData {
  todoId: number;
  title: string;
  status: TodoStatus;
  segments: GanttSegment[];
  isInserted: boolean;
  reorderReason: string;
}

interface TickMark {
  time: number;
  label: string;
  percent: number;
}

const EXPORT_MIN_WIDTH = 1400;

// --- Utility functions ---

function isoToMs(iso: string): number {
  return new Date(iso).getTime();
}

function formatDuration(ms: number): string {
  if (ms <= 0) return '0分';
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    return `${days}天${hours % 24}时`;
  }
  if (hours > 0) return `${hours}时${minutes}分`;
  return `${minutes}分`;
}

function formatShortDate(ms: number): string {
  const d = new Date(ms);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function formatDateTime(ms: number): string {
  return new Date(ms).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// --- Core algorithm ---

function buildGanttData(todos: Todo[], timeSegmentsMap: Record<number, TimeSegment[]> = {}) {
  const now = Date.now();
  const sorted = [...todos].sort((a, b) => a.sort_order - b.sort_order);

  const bars: GanttBarData[] = sorted.map((todo) => {
    const isInserted = !!todo.reorder_reason;
    const segments: GanttSegment[] = [];
    const dbSegments = timeSegmentsMap[todo.id];

    if (dbSegments && dbSegments.length > 0) {
      for (const seg of dbSegments) {
        const startMs = isoToMs(seg.started_at);
        const endMs = seg.ended_at ? isoToMs(seg.ended_at) : now;
        if (endMs >= startMs) {
          segments.push({ startTime: startMs, endTime: endMs });
        }
      }
    }

    if (segments.length === 0) {
      const createdMs = isoToMs(todo.created_at);
      const updatedMs = isoToMs(todo.updated_at);
      switch (todo.status) {
        case 'done':
          segments.push({ startTime: createdMs, endTime: updatedMs });
          break;
        case 'doing':
          segments.push({ startTime: createdMs, endTime: now });
          break;
        default:
          segments.push({ startTime: updatedMs, endTime: updatedMs });
          break;
      }
    }

    return {
      todoId: todo.id,
      title: todo.title || todo.content || `Todo #${todo.id}`,
      status: todo.status,
      segments,
      isInserted,
      reorderReason: todo.reorder_reason,
    };
  });

  const allTimes = bars.flatMap((b) => b.segments.flatMap((s) => [s.startTime, s.endTime]));
  if (allTimes.length === 0) {
    return { bars, ticks: [], timeStart: now, timeEnd: now, totalMs: 1 };
  }

  const rawStart = Math.min(...allTimes);
  const rawEnd = Math.max(...allTimes);
  const padding = Math.max((rawEnd - rawStart) * 0.05, 1800000);
  const timeStart = rawStart - padding;
  const timeEnd = rawEnd + padding;
  const totalMs = timeEnd - timeStart;

  const totalDays = totalMs / 86400000;
  let tickInterval: number;
  if (totalDays <= 3) tickInterval = 86400000;
  else if (totalDays <= 14) tickInterval = 86400000 * 2;
  else if (totalDays <= 60) tickInterval = 86400000 * 7;
  else tickInterval = 86400000 * 14;

  const ticks: TickMark[] = [];
  const firstTick = new Date(timeStart);
  firstTick.setHours(0, 0, 0, 0);
  firstTick.setDate(firstTick.getDate() + 1);
  let tickTime = firstTick.getTime();

  while (tickTime < timeEnd) {
    ticks.push({
      time: tickTime,
      label: formatShortDate(tickTime),
      percent: ((tickTime - timeStart) / totalMs) * 100,
    });
    tickTime += tickInterval;
  }

  return { bars, ticks, timeStart, timeEnd, totalMs };
}

// --- Sub-components ---

const STATUS_COLORS: Record<TodoStatus, { bar: string; glow: string; label: string }> = {
  done: {
    bar: 'bg-emerald-500/80',
    glow: 'shadow-emerald-500/30',
    label: '已完成',
  },
  doing: {
    bar: 'bg-blue-500/80',
    glow: 'shadow-blue-500/30',
    label: '进行中',
  },
  pending: {
    bar: 'bg-yellow-500/40',
    glow: '',
    label: '待处理',
  },
};

function GanttRow({
  bar,
  timeStart,
  totalMs,
  onSelect,
  isSelected,
  labelWidth,
}: {
  bar: GanttBarData;
  timeStart: number;
  totalMs: number;
  onSelect: (id: number) => void;
  isSelected: boolean;
  labelWidth: number;
}) {
  const isActive = bar.status !== 'pending';
  const cfg = STATUS_COLORS[bar.status];
  const totalDuration = bar.segments.reduce((sum, s) => sum + (s.endTime - s.startTime), 0);

  // Compute left position for tooltip from first segment
  const firstSeg = bar.segments[0];
  const firstLeft = firstSeg
    ? ((firstSeg.startTime - timeStart) / totalMs) * 100
    : 0;

  return (
    <div
      className={`flex items-center h-10 cursor-pointer transition-colors gantt-row ${
        isSelected ? 'bg-gray-800/80' : 'hover:bg-gray-800/40'
      }`}
      onClick={() => onSelect(bar.todoId)}
    >
      {/* Label */}
      <div
        className="flex-shrink-0 h-full px-3 border-r border-gray-700/30"
        data-gantt-label
        style={{ width: labelWidth }}
      >
        <div className="flex h-full min-w-0 items-center">
          <span
            className="flex min-w-0 items-center truncate text-xs leading-none text-gray-300"
            data-gantt-label-text
            title={bar.title}
          >
            {bar.title}
          </span>
        </div>
      </div>

      {/* Bar area */}
      <div className="flex-1 relative h-full group">
        {isActive && bar.segments.length > 0 ? (
          bar.segments.map((seg, idx) => {
            const leftPercent = ((seg.startTime - timeStart) / totalMs) * 100;
            const widthPercent = Math.max(((seg.endTime - seg.startTime) / totalMs) * 100, 0.5);
            const isMulti = bar.segments.length > 1;
            return (
              <div
                key={idx}
                className="absolute inset-y-0 flex items-center"
                data-gantt-bar-shell
                style={{ left: `${leftPercent}%`, width: `${widthPercent}%` }}
              >
                <div
                  className={`relative flex h-5 items-center rounded-sm ${cfg.bar} shadow-sm ${cfg.glow} gantt-bar-animate group-hover:brightness-125 transition-all ${isMulti ? 'opacity-80' : ''}`}
                  data-gantt-animated
                  data-gantt-bar-box
                  style={{ width: '100%' }}
                >
                  {widthPercent > 10 && idx === 0 && (
                    <span
                      className="block truncate px-1.5 text-[10px] leading-none text-white/90"
                      data-gantt-duration-text
                    >
                      {formatDuration(totalDuration)}
                    </span>
                  )}
                  {bar.isInserted && idx === 0 && (
                    <div className="absolute -left-[5px] top-1/2 -translate-y-1/2 w-2.5 h-2.5 bg-orange-400 rotate-45 z-10 shadow-sm shadow-orange-400/50" />
                  )}
                </div>
              </div>
            );
          })
        ) : (
          bar.segments.length > 0 && bar.segments[0] && (
            <div
              className="absolute inset-y-0 flex items-center"
              style={{ left: `${((bar.segments[0].startTime - timeStart) / totalMs) * 100}%` }}
            >
              <div className="w-2.5 h-2.5 rotate-45 bg-yellow-400/50 border border-yellow-400/70" />
            </div>
          )
        )}

        {/* Tooltip */}
        <div
          className="absolute z-30 opacity-0 group-hover:opacity-100 pointer-events-none bottom-full mb-2 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs shadow-xl whitespace-nowrap transition-opacity"
          style={{ left: `max(${firstLeft}%, 40%)` }}
        >
          <div className="font-medium text-gray-100">{bar.title}</div>
          <div className="text-gray-400 mt-0.5">
            {cfg.label}
            {bar.isInserted && <span className="text-orange-300 ml-2">已插入</span>}
          </div>
          {isActive ? (
            <>
              {bar.segments.map((seg, idx) => (
                <div key={idx} className="text-gray-400 mt-0.5">
                  {bar.segments.length > 1 && `第${idx + 1}段: `}
                  {formatDateTime(seg.startTime)} → {formatDateTime(seg.endTime)}
                  <span className="ml-2 text-gray-500">({formatDuration(seg.endTime - seg.startTime)})</span>
                </div>
              ))}
              <div className="text-gray-400 mt-0.5 border-t border-gray-700 pt-0.5">总耗时: {formatDuration(totalDuration)}</div>
            </>
          ) : (
            <div className="text-gray-500 mt-0.5">未开始</div>
          )}
          {bar.isInserted && bar.reorderReason && (
            <div className="text-orange-300/80 mt-0.5 border-t border-gray-700 pt-1">
              原因: {bar.reorderReason}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Main component ---

export default function GanttChart({ todos, onSelect, selectedId }: GanttChartProps) {
  const [timeSegmentsMap, setTimeSegmentsMap] = useState<Record<number, TimeSegment[]>>({});

  useEffect(() => {
    if (todos.length === 0) return;
    const ids = todos.map(t => t.id);
    fetchAllTimeSegments(ids)
      .then(setTimeSegmentsMap)
      .catch(() => setTimeSegmentsMap({}));
  }, [todos]);

  const { bars, ticks, timeStart, timeEnd, totalMs } = useMemo(
    () => buildGanttData(todos, timeSegmentsMap),
    [todos, timeSegmentsMap],
  );

  const nowPercent = totalMs > 0 ? ((Date.now() - timeStart) / totalMs) * 100 : 0;

  // Resizable label column
  const [labelWidth, setLabelWidth] = useState(180);
  const resizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const chartRef = useRef<HTMLDivElement>(null);
  const [isExporting, setIsExporting] = useState(false);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = labelWidth;

    const handleMouseMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const delta = ev.clientX - startXRef.current;
      const newWidth = Math.max(100, Math.min(500, startWidthRef.current + delta));
      setLabelWidth(newWidth);
    };

    const handleMouseUp = () => {
      resizingRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [labelWidth]);

  // Export as image
  const handleExportImage = useCallback(async () => {
    if (!chartRef.current || isExporting) return;

    setIsExporting(true);
    try {
      const html2canvas = (await import('html2canvas')).default;
      const exportRoot = chartRef.current.cloneNode(true) as HTMLDivElement;
      const exportWidth = Math.max(chartRef.current.scrollWidth, labelWidth + 960, EXPORT_MIN_WIDTH);
      exportRoot.dataset.ganttExportClone = 'true';

      Object.assign(exportRoot.style, {
        position: 'fixed',
        left: '-9999px',
        top: '0',
        width: `${exportWidth}px`,
        height: 'auto',
        minHeight: '0',
        maxHeight: 'none',
        overflow: 'visible',
        background: '#111827',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-scroll]').forEach((node) => {
        Object.assign(node.style, {
          overflow: 'visible',
          height: 'auto',
          maxHeight: 'none',
          flex: 'none',
        });
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-flex-body]').forEach((node) => {
        Object.assign(node.style, {
          minHeight: '0',
          height: 'auto',
          flex: 'none',
        });
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-animated]').forEach((node) => {
        node.style.animation = 'none';
        node.style.transition = 'none';
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-label]').forEach((node) => {
        node.style.overflow = 'visible';
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-label-text]').forEach((node) => {
        node.style.display = 'flex';
        node.style.alignItems = 'center';
        node.style.height = '100%';
        node.style.lineHeight = '1';
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-bar-shell]').forEach((node) => {
        node.style.top = '0';
        node.style.bottom = '0';
        node.style.display = 'flex';
        node.style.alignItems = 'center';
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-bar-box]').forEach((node) => {
        node.style.display = 'flex';
        node.style.alignItems = 'center';
        node.style.height = '20px';
        node.style.boxSizing = 'border-box';
        node.style.overflow = 'visible';
      });

      exportRoot.querySelectorAll<HTMLElement>('[data-gantt-duration-text]').forEach((node) => {
        node.style.display = 'flex';
        node.style.alignItems = 'center';
        node.style.height = '20px';
        node.style.lineHeight = '20px';
        node.style.overflow = 'visible';
        node.style.paddingTop = '0';
        node.style.paddingBottom = '0';
        node.style.marginTop = '0';
        node.style.marginBottom = '0';
        node.style.boxSizing = 'border-box';
      });

      document.body.appendChild(exportRoot);
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

      const canvas = await html2canvas(exportRoot, {
        backgroundColor: '#111827',
        scale: Math.min(window.devicePixelRatio || 1, 2),
        useCORS: true,
        width: exportWidth,
        height: exportRoot.scrollHeight,
        windowWidth: exportWidth,
        windowHeight: exportRoot.scrollHeight,
        scrollX: 0,
        scrollY: 0,
      });

      exportRoot.remove();

      const link = document.createElement('a');
      link.download = `gantt-${new Date().toISOString().slice(0, 10)}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      document.querySelectorAll('[data-gantt-export-clone="true"]').forEach((node) => node.remove());
      setIsExporting(false);
    }
  }, [isExporting, labelWidth]);

  if (bars.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
        没有数据可显示
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Toolbar: Legend + Export */}
      <div className="px-4 pt-3 pb-2 flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-3 text-[10px] text-gray-400">
          <span className="flex items-center gap-1.5">
            <span className="w-3.5 h-2 rounded-sm bg-blue-500/80" />
            进行中
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3.5 h-2 rounded-sm bg-emerald-500/80" />
            已完成
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rotate-45 bg-yellow-400/50 border border-yellow-400/70" />
            待处理
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rotate-45 bg-orange-400" />
            插入
          </span>
        </div>
        <button
          type="button"
          onClick={handleExportImage}
          disabled={isExporting}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-gray-300 bg-gray-800 border border-gray-700/50 rounded-lg hover:bg-gray-700 hover:border-gray-600 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <svg className={`w-3.5 h-3.5 ${isExporting ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          {isExporting ? '导出中...' : '导出图片'}
        </button>
      </div>

      {/* Chart container for export */}
      <div ref={chartRef} className="flex flex-col flex-1 min-h-0 bg-gray-900" data-gantt-export-root="true">
        {/* Timeline header */}
        <div className="flex-shrink-0 border-b border-gray-700/50">
          <div className="flex">
            <div className="flex-shrink-0 border-r border-gray-700/30" style={{ width: labelWidth }} />
            <div className="flex-1 relative h-7 flex items-end pb-1">
              {ticks.map((tick, i) => (
                <span
                  key={i}
                  className="absolute text-[10px] text-gray-500 -translate-x-1/2"
                  style={{ left: `${tick.percent}%` }}
                >
                  {tick.label}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Chart body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin" data-gantt-scroll>
          <div className="relative" data-gantt-flex-body>
            {/* Vertical grid lines */}
            {ticks.map((tick, i) => (
              <div
                key={`grid-${i}`}
                className="absolute top-0 bottom-0 w-px bg-gray-700/30"
                style={{
                  left: `calc(${labelWidth}px + (100% - ${labelWidth}px) * ${tick.percent / 100})`,
                }}
              />
            ))}

            {/* Today marker line */}
            {nowPercent >= 0 && nowPercent <= 100 && (
              <div
                className="absolute top-0 bottom-0 w-0.5 border-l border-dashed border-red-400/50 gantt-today-marker z-10"
                data-gantt-animated
                style={{
                  left: `calc(${labelWidth}px + (100% - ${labelWidth}px) * ${nowPercent / 100})`,
                }}
              />
            )}

            {/* Rows */}
            {bars.map((bar) => (
              <GanttRow
                key={bar.todoId}
                bar={bar}
                timeStart={timeStart}
                totalMs={totalMs}
                onSelect={onSelect}
                isSelected={bar.todoId === selectedId}
                labelWidth={labelWidth}
              />
            ))}
          </div>
        </div>

        {/* Footer info */}
        <div className="px-4 py-2 flex-shrink-0 border-t border-gray-700/50">
          <span className="text-[10px] text-gray-500">
            共 {bars.length} 项 · 时间范围 {formatDuration(timeEnd - timeStart)}
          </span>
        </div>
      </div>

      {/* Resize handle */}
      <div
        className="absolute top-0 bottom-0 w-2 cursor-col-resize z-20 hover:bg-blue-500/20 transition-colors"
        style={{ left: labelWidth - 1 }}
        onMouseDown={handleResizeMouseDown}
      />
    </div>
  );
}
