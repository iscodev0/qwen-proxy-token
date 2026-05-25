import type { QwenCredentials, QwenToken, QwenModel, Message } from "../types";

const QWEN_BASE_URL = "https://chat.qwen.ai";
const QWEN_API_URL = `${QWEN_BASE_URL}/api/v2`;

const DEFAULT_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  Accept: "application/json",
  "Accept-Language": "en-US,en;q=0.9",
  "Content-Type": "application/json",
  Origin: QWEN_BASE_URL,
  Referer: `${QWEN_BASE_URL}/`,
};

export class QwenSessionExpiredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QwenSessionExpiredError";
  }
}

export class QwenProviderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QwenProviderError";
  }
}

export class QwenProvider {
  private token: QwenToken | null = null;
  private modelsCache: QwenModel[] | null = null;
  private modelsCacheTime: Date | null = null;
  private retries: number;

  constructor(retries = 2) {
    this.retries = retries;
  }

  setToken(jwtToken: string): void {
    const parts = jwtToken.split('.');
    if (parts.length !== 3 || !parts[1]) {
      throw new QwenProviderError("Invalid JWT token format");
    }

    try {
      const payload = JSON.parse(atob(parts[1]));
      const expiresAt = new Date(payload.exp * 1000);
      
      this.token = {
        token: jwtToken,
        expiresAt,
      };

      console.log(`Qwen token set, expires: ${expiresAt.toISOString()}`);
    } catch (error) {
      throw new QwenProviderError("Failed to parse JWT token");
    }
  }

  private async ensureToken(credentials: QwenCredentials): Promise<string> {
    const { token } = credentials;

    if (!token) {
      throw new QwenProviderError("Credentials must contain 'token' (JWT)");
    }

    if (this.token && new Date() < this.token.expiresAt) {
      return this.token.token;
    }

    this.setToken(token);
    return this.token!.token;
  }

  private getHeaders(token: string): Record<string, string> {
    return {
      ...DEFAULT_HEADERS,
      Authorization: `Bearer ${token}`,
    };
  }

  async fetchModels(token: string): Promise<QwenModel[]> {
    if (this.modelsCache && this.modelsCacheTime) {
      const cacheAge = Date.now() - this.modelsCacheTime.getTime();
      if (cacheAge < 60 * 60 * 1000) {
        return this.modelsCache;
      }
    }

    const headers = this.getHeaders(token);

    const response = await fetch(`${QWEN_API_URL}/models`, {
      headers,
    });

    if (!response.ok) {
      console.warn("Failed to fetch models, using defaults");
      return this.defaultModels();
    }

    const data: any = await response.json();
    const modelsData = data.data?.data || [];

    this.modelsCache = modelsData;
    this.modelsCacheTime = new Date();

    console.log(`Cached ${modelsData.length} models from Qwen API`);
    return modelsData;
  }

  private defaultModels(): QwenModel[] {
    return [
      {
        id: "qwen3.7-max",
        name: "Qwen3.7-Max",
        object: "model",
        owned_by: "qwen",
      },
      {
        id: "qwen3.6-plus",
        name: "Qwen3.6-Plus",
        object: "model",
        owned_by: "qwen",
      },
      {
        id: "qwen3.6-max-preview",
        name: "Qwen3.6-Max-Preview",
        object: "model",
        owned_by: "qwen",
      },
    ];
  }

  private async createChat(token: string, model: string): Promise<string> {
    const headers = this.getHeaders(token);

    const response = await fetch(`${QWEN_API_URL}/chats/new`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        title: "New Chat",
        models: [model],
        chat_mode: "normal",
        chat_type: "t2t",
        timestamp: Date.now(),
        project_id: "",
      }),
    });

    if (!response.ok) {
      throw new QwenProviderError(`Failed to create chat: HTTP ${response.status}`);
    }

    const data: any = await response.json();
    const chatId = data.data?.id;

    if (!chatId) {
      throw new QwenProviderError("Failed to create chat: no ID returned");
    }

    console.log(`Created new chat: ${chatId}`);
    return chatId;
  }

  private buildChatPayload(
    model: string,
    messages: Message[],
    chatId: string,
    stream: boolean
  ) {
    const qwenMessages: any[] = [];
    
    messages.forEach((msg, idx) => {
      const fid = crypto.randomUUID();
      const parentId = idx === 0 ? null : qwenMessages[idx - 1]?.fid || null;
      
      qwenMessages.push({
        fid,
        parentId,
        childrenIds: [],
        role: msg.role,
        content: msg.content,
        user_action: msg.role === "user" ? "chat" : "assistant",
        files: [],
        timestamp: Math.floor(Date.now() / 1000),
        models: msg.role === "user" ? [model] : [],
        chat_type: "t2t",
        feature_config: {
          thinking_enabled: true,
          output_schema: "phase",
          research_mode: "normal",
        },
        extra: {
          meta: {
            subChatType: "t2t",
          },
        },
        sub_chat_type: "t2t",
      });
    });

    return {
      stream,
      version: "2.1",
      incremental_output: true,
      chat_id: chatId,
      chat_mode: "normal",
      model,
      parent_id: null,
      messages: qwenMessages,
      timestamp: Math.floor(Date.now() / 1000),
    };
  }

  async chatCompletion(
    credentials: QwenCredentials,
    model: string,
    messages: Message[]
  ): Promise<{ chatId: string; content: string }> {
    const token = await this.ensureToken(credentials);

    const cleanModel = model.startsWith("qwen/") ? model.substring(5) : model;
    const chatId = await this.createChat(token, cleanModel);

    const processedMessages: Message[] = [];
    let systemContent: string | null = null;

    for (const m of messages) {
      if (m.role === "system") {
        systemContent = m.content;
      } else {
        processedMessages.push({ role: m.role, content: m.content });
      }
    }

    if (systemContent && processedMessages.length > 0) {
      for (let i = 0; i < processedMessages.length; i++) {
        const msg = processedMessages[i];
        if (msg && msg.role === "user") {
          processedMessages[i] = {
            role: "user",
            content: `${systemContent}\n\n${msg.content}`,
          };
          break;
        }
      }
    }

    const payload = this.buildChatPayload(cleanModel, processedMessages, chatId, true);
    const headers = this.getHeaders(token);

    const response = await fetch(`${QWEN_API_URL}/chat/completions?chat_id=${chatId}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (response.status === 401 || response.status === 403) {
      this.token = null;
      throw new QwenSessionExpiredError(
        `Qwen session expired (HTTP ${response.status})`
      );
    }

    if (!response.ok) {
      const text = await response.text();
      throw new QwenProviderError(
        `Qwen returned HTTP ${response.status}: ${text.substring(0, 500)}`
      );
    }

    // Read the SSE stream and collect full content
    if (!response.body) {
      throw new QwenProviderError("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        const dataStr = trimmed.substring(6);
        if (dataStr === "[DONE]") {
          return { chatId, content: fullContent };
        }

        try {
          const data: any = JSON.parse(dataStr);
          const choices = data.choices || [];
          if (choices.length > 0) {
            const delta = choices[0].delta || {};
            const text = delta.content || delta.text || "";
            const phase = delta.phase || "";
            
            if (text && phase === "answer") {
              fullContent += text;
            }
          }
        } catch {
          continue;
        }
      }
    }

    return { chatId, content: fullContent };
  }

  async *chatCompletionStream(
    credentials: QwenCredentials,
    model: string,
    messages: Message[]
  ): AsyncGenerator<{ content?: string; finish?: string }> {
    const token = await this.ensureToken(credentials);

    const cleanModel = model.startsWith("qwen/") ? model.substring(5) : model;
    const chatId = await this.createChat(token, cleanModel);

    const processedMessages: Message[] = [];
    let systemContent: string | null = null;

    for (const m of messages) {
      if (m.role === "system") {
        systemContent = m.content;
      } else {
        processedMessages.push({ role: m.role, content: m.content });
      }
    }

    if (systemContent && processedMessages.length > 0) {
      for (let i = 0; i < processedMessages.length; i++) {
        const msg = processedMessages[i];
        if (msg && msg.role === "user") {
          processedMessages[i] = {
            role: "user",
            content: `${systemContent}\n\n${msg.content}`,
          };
          break;
        }
      }
    }

    const payload = this.buildChatPayload(cleanModel, processedMessages, chatId, true);
    const headers = this.getHeaders(token);

    const response = await fetch(`${QWEN_API_URL}/chat/completions?chat_id=${chatId}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (response.status === 401 || response.status === 403) {
      this.token = null;
      throw new QwenSessionExpiredError(
        `Qwen session expired (HTTP ${response.status})`
      );
    }

    if (!response.ok) {
      const text = await response.text();
      throw new QwenProviderError(
        `Qwen returned HTTP ${response.status}: ${text.substring(0, 500)}`
      );
    }

    if (!response.body) {
      throw new QwenProviderError("Response body is null");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        const dataStr = trimmed.substring(6);
        if (dataStr === "[DONE]") {
          yield { finish: "stop" };
          return;
        }

        try {
          const data: any = JSON.parse(dataStr);
          const choices = data.choices || [];
          if (choices.length > 0) {
            const delta = choices[0].delta || {};
            const text = delta.content || delta.text || "";
            const phase = delta.phase || "";
            const finish = choices[0].finish_reason;

            if (text && phase === "answer") {
              yield { content: text };
            }
            if (finish) {
              yield { finish };
              return;
            }
          }
        } catch {
          continue;
        }
      }
    }

    yield { finish: "stop" };
  }

  async listModels(): Promise<QwenModel[]> {
    if (this.modelsCache) {
      return this.modelsCache;
    }
    return this.defaultModels();
  }

  validateCredentials(credentials: QwenCredentials): boolean {
    const { token } = credentials;

    if (!token) return false;
    if (typeof token !== "string") return false;
    
    const parts = token.split('.');
    if (parts.length !== 3 || !parts[1]) return false;
    
    try {
      const payload = JSON.parse(atob(parts[1]));
      if (!payload.exp) return false;
      
      const expiresAt = new Date(payload.exp * 1000);
      if (expiresAt <= new Date()) return false;
      
      return true;
    } catch {
      return false;
    }
  }
}
