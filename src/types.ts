export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
}

export interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

export interface Tool {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters?: any;
  };
}

export interface ChatCompletionRequest {
  model: string;
  messages: Message[];
  stream?: boolean;
  temperature?: number;
  max_tokens?: number;
  tools?: Tool[];
  tool_choice?: "auto" | "none" | "required" | { type: "function"; function: { name: string } };
}

export interface ChatCompletionResponse {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: {
    index: number;
    message: {
      role: "assistant";
      content: string;
    };
    finish_reason: string;
  }[];
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface ChatCompletionChunk {
  id: string;
  object: "chat.completion.chunk";
  created: number;
  model: string;
  choices: {
    index: number;
    delta: {
      role?: "assistant";
      content?: string;
    };
    finish_reason: string | null;
  }[];
}

export interface Model {
  id: string;
  object: "model";
  created: number;
  owned_by: string;
}

export interface ModelList {
  object: "list";
  data: Model[];
}

export interface QwenCredentials {
  token: string;
}

export interface QwenToken {
  token: string;
  expiresAt: Date;
}

export interface QwenModel {
  id: string;
  name: string;
  object: string;
  owned_by: string;
  info?: {
    meta?: {
      short_description?: string;
      description?: string;
    };
  };
}
