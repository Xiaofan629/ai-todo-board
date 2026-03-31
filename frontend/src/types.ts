// --- Todo types ---

export type TodoStatus = 'pending' | 'doing' | 'done';

export interface Todo {
  id: number;
  title: string;
  content: string;
  status: TodoStatus;
  is_processing: boolean;
  sort_order: number;
  reorder_reason: string;
  userid: string;
  chatid: string;
  chattype: string;
  created_at: string;
  updated_at: string;
}

// --- Message types ---

export type MessageRole = 'user' | 'assistant' | 'tool' | 'system';

export interface Message {
  id: number;
  todo_id: number;
  role: MessageRole;
  content: string;
  tool_name: string;
  tool_input: string;
  event_type: string;
  event_subtype: string;
  payload: string;
  created_at: string;
}

// --- Stats type ---

export interface Stats {
  pending: number;
  doing: number;
  done: number;
}

// --- API response types ---

export interface ChatResponse {
  status: string;
  response: string;
}
