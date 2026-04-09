import type { Todo, Message, Stats, ChatResponse, TodoStatus, TimeSegment } from './types';

const API_BASE = './api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`API error ${response.status}: ${text}`);
  }

  return response.json() as Promise<T>;
}

/** Fetch all todos, optionally filtered by status. */
export async function fetchTodos(status?: TodoStatus): Promise<Todo[]> {
  const params = status ? `?status=${status}` : '';
  return request<Todo[]>(`/todos${params}`);
}

/** Fetch messages for a specific todo. */
export async function fetchMessages(todoId: number): Promise<Message[]> {
  return request<Message[]>(`/todos/${todoId}/messages`);
}

/** Send a chat message to continue the conversation on a todo. */
export async function sendChat(todoId: number, content: string): Promise<ChatResponse> {
  return request<ChatResponse>(`/todos/${todoId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

/** Fetch dashboard statistics. */
export async function fetchStats(): Promise<Stats> {
  return request<Stats>('/stats');
}

/** Mark a todo as completed. Auto-promotes next pending to doing. */
export async function completeTodo(todoId: number): Promise<{ status: string; next_doing_id?: number }> {
  return request<{ status: string; next_doing_id?: number }>(`/todos/${todoId}/complete`, {
    method: 'POST',
  });
}

/** Reorder a todo relative to another visible card. */
export async function reorderTodo(
  todoId: number,
  targetTodoId: number,
  position: 'top' | 'bottom',
  reason?: string,
  promoteToDoing?: boolean,
): Promise<{ status: string }> {
  return request<{ status: string }>(`/todos/${todoId}/reorder`, {
    method: 'POST',
    body: JSON.stringify({
      target_todo_id: targetTodoId,
      position,
      reason: reason || '',
      promote_to_doing: promoteToDoing ?? false,
    }),
  });
}

/** Fetch time segments for a specific todo. */
export async function fetchTimeSegments(todoId: number): Promise<TimeSegment[]> {
  return request<TimeSegment[]>(`/todos/${todoId}/time-segments`);
}

/** Fetch time segments for multiple todos. */
export async function fetchAllTimeSegments(todoIds: number[]): Promise<Record<number, TimeSegment[]>> {
  if (todoIds.length === 0) return {};
  return request<Record<number, TimeSegment[]>>(`/time-segments?todo_ids=${todoIds.join(',')}`);
}

/** Move a pending todo to the top of the queue and promote it to doing. */
export async function startDoingTodo(todoId: number, reason?: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/todos/${todoId}/reorder`, {
    method: 'POST',
    body: JSON.stringify({
      target_index: 0,
      position: 'top',
      reason: reason || '',
      promote_to_doing: true,
    }),
  });
}

/** Mark a pending todo as completed with timing logic. */
export async function completeTodoFromPending(todoId: number): Promise<{ status: string; next_doing_id?: number }> {
  return request<{ status: string; next_doing_id?: number }>(`/todos/${todoId}/complete-from-pending`, {
    method: 'POST',
  });
}

/** Delete a todo permanently. */
export async function deleteTodo(todoId: number): Promise<{ status: string }> {
  return request<{ status: string }>(`/todos/${todoId}`, { method: 'DELETE' });
}

/** Update a todo's title. */
export async function updateTodoTitle(todoId: number, title: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/todos/${todoId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}
