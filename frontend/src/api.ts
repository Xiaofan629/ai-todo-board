import type { Todo, Message, Stats, ChatResponse, TodoStatus } from './types';

const API_BASE = '/api';

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
