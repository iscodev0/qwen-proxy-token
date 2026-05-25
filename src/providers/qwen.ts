import type { QwenCredentials, QwenToken, QwenModel, Message, Tool, ToolCall } from "../types";

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

interface ActiveSession {
  chatId: string;
  model: string;
  messageCount: number;
  lastFid: string | null;
}

export class QwenProvider {
  private token: QwenToken | null = null;
  private modelsCache: QwenModel[] | null = null;
  private modelsCacheTime: Date | null = null;
  private retries: number;
  private activeSession: ActiveSession | null = null;

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

  private async getOrCreateSession(token: string, model: string, messageCount: number): Promise<{ chatId: string; isNew: boolean }> {
    if (
      this.activeSession &&
      this.activeSession.model === model &&
      messageCount > this.activeSession.messageCount
    ) {
      console.log(`Reusing chat: ${this.activeSession.chatId} (messages: ${this.activeSession.messageCount} → ${messageCount})`);
      return { chatId: this.activeSession.chatId, isNew: false };
    }

    const chatId = await this.createChat(token, model);
    this.activeSession = {
      chatId,
      model,
      messageCount: 0,
      lastFid: null,
    };
    return { chatId, isNew: true };
  }

  private updateSession(messageCount: number, lastFid: string | null): void {
    if (this.activeSession) {
      this.activeSession.messageCount = messageCount;
      this.activeSession.lastFid = lastFid;
    }
  }

  private buildChatPayload(
    model: string,
    messages: Message[],
    chatId: string,
    stream: boolean,
    tools?: Tool[],
    toolChoice?: "auto" | "none" | "required" | { type: "function"; function: { name: string } }
  ) {
    const qwenMessages: any[] = [];
    
    messages.forEach((msg, idx) => {
      const fid = crypto.randomUUID();
      const parentId = idx === 0 ? null : qwenMessages[idx - 1]?.fid || null;

      const roleMap: Record<string, string> = {
        user: "user",
        assistant: "assistant",
        system: "system",
        tool: "tool",
      };

      const actionMap: Record<string, string> = {
        user: "chat",
        assistant: "assistant",
        system: "system",
        tool: "tool",
      };
      
      qwenMessages.push({
        fid,
        parentId,
        childrenIds: [],
        role: roleMap[msg.role] || msg.role,
        content: msg.content,
        user_action: actionMap[msg.role] || "chat",
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

    const lastMsg = qwenMessages[qwenMessages.length - 1];
    const payload: any = {
      stream,
      version: "2.1",
      incremental_output: true,
      chat_id: chatId,
      chat_mode: "normal",
      model,
      parent_id: lastMsg?.parentId || null,
      messages: qwenMessages,
      timestamp: Math.floor(Date.now() / 1000),
    };

    if (tools && tools.length > 0) {
      payload.tools = tools.map(tool => ({
        type: tool.type,
        function: tool.function
      }));
      
      if (toolChoice) {
        payload.tool_choice = toolChoice;
      }
    }

    return payload;
  }

  private toolsToPrompt(tools: Tool[]): string {
    if (!tools || tools.length === 0) return "";
    
    let prompt = "\n\nYou have access to the following tools:\n\n";
    
    for (const tool of tools) {
      prompt += `## ${tool.function.name}\n`;
      if (tool.function.description) {
        prompt += `${tool.function.description}\n`;
      }
      if (tool.function.parameters) {
        prompt += `Parameters: ${JSON.stringify(tool.function.parameters, null, 2)}\n`;
      }
      prompt += "\n";
    }
    
    prompt += `To use a tool, respond with a JSON block in this exact format:
\`\`\`json
{
  "tool": "tool_name",
  "parameters": {
    "param1": "value1",
    "param2": "value2"
  }
}
\`\`\`

You can use multiple tools in sequence if needed. After using a tool, wait for the result before continuing.`;
    
    return prompt;
  }

  private parseToolCalls(content: string): ToolCall[] | undefined {
    const toolCalls: ToolCall[] = [];
    const jsonBlockRegex = /```json\s*({[\s\S]*?})\s*```/g;
    
    let match;
    while ((match = jsonBlockRegex.exec(content)) !== null) {
      try {
        if (!match[1]) continue;
        const parsed = JSON.parse(match[1]);
        if (parsed.tool && typeof parsed.tool === "string") {
          toolCalls.push({
            id: `call_${crypto.randomUUID().substring(0, 12)}`,
            type: "function",
            function: {
              name: parsed.tool,
              arguments: JSON.stringify(parsed.parameters || {}),
            },
          });
        }
      } catch {
        continue;
      }
    }
    
    return toolCalls.length > 0 ? toolCalls : undefined;
  }

  async chatCompletion(
    credentials: QwenCredentials,
    model: string,
    messages: Message[],
    tools?: Tool[],
    toolChoice?: "auto" | "none" | "required" | { type: "function"; function: { name: string } }
  ): Promise<{ chatId: string; content: string; toolCalls?: ToolCall[] }> {
    const token = await this.ensureToken(credentials);

    const cleanModel = model.startsWith("qwen/") ? model.substring(5) : model;
    const { chatId } = await this.getOrCreateSession(token, cleanModel, messages.length);

    const hasUserMessage = messages.some(m => m.role === "user");
    if (!hasUserMessage) {
      throw new QwenProviderError("No user message found");
    }

    let processedMessages: Message[] = [...messages];

    if (tools && tools.length > 0 && toolChoice !== "none") {
      const toolsPrompt = this.toolsToPrompt(tools);
      processedMessages = processedMessages.map(m => {
        if (m.role === "system") {
          return { ...m, content: m.content + toolsPrompt };
        }
        return m;
      });
      if (!processedMessages.some(m => m.role === "system")) {
        processedMessages.unshift({ role: "system", content: toolsPrompt.trim() });
      }
    }

    const payload = this.buildChatPayload(cleanModel, processedMessages, chatId, false, tools, toolChoice);
    const headers = this.getHeaders(token);

    const response = await fetch(`${QWEN_API_URL}/chat/completions?chat_id=${chatId}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (response.status === 401 || response.status === 403) {
      this.token = null;
      this.activeSession = null;
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
    let fullContent = "";

    try {
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
            this.updateSession(messages.length, null);
            const toolCalls = this.parseToolCalls(fullContent);
            let cleanContent = fullContent;
            if (toolCalls) {
              cleanContent = fullContent.replace(/```json\s*{[\s\S]*?}\s*```/g, "").trim();
            }
            return { chatId, content: cleanContent, toolCalls };
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
    } finally {
      reader.releaseLock();
    }

    this.updateSession(messages.length, null);
    const toolCalls = this.parseToolCalls(fullContent);
    let cleanContent = fullContent;
    if (toolCalls) {
      cleanContent = fullContent.replace(/```json\s*{[\s\S]*?}\s*```/g, "").trim();
    }
    
    return { chatId, content: cleanContent, toolCalls };
  }

  async *chatCompletionStream(
    credentials: QwenCredentials,
    model: string,
    messages: Message[],
    tools?: Tool[],
    toolChoice?: "auto" | "none" | "required" | { type: "function"; function: { name: string } }
  ): AsyncGenerator<{ content?: string; finish?: string; toolCalls?: ToolCall[] }> {
    const token = await this.ensureToken(credentials);

    const cleanModel = model.startsWith("qwen/") ? model.substring(5) : model;
    const { chatId } = await this.getOrCreateSession(token, cleanModel, messages.length);

    const hasUserMessage = messages.some(m => m.role === "user");
    if (!hasUserMessage) {
      throw new QwenProviderError("No user message found");
    }

    let processedMessages: Message[] = [...messages];

    if (tools && tools.length > 0 && toolChoice !== "none") {
      const toolsPrompt = this.toolsToPrompt(tools);
      processedMessages = processedMessages.map(m => {
        if (m.role === "system") {
          return { ...m, content: m.content + toolsPrompt };
        }
        return m;
      });
      if (!processedMessages.some(m => m.role === "system")) {
        processedMessages.unshift({ role: "system", content: toolsPrompt.trim() });
      }
    }

    const payload = this.buildChatPayload(cleanModel, processedMessages, chatId, true, tools, toolChoice);
    const headers = this.getHeaders(token);

    console.log(`\n=== Sending to Qwen ===`);
    console.log(`Chat ID: ${chatId}`);
    console.log(`Messages: ${processedMessages.length}`);
    console.log(`Roles: ${processedMessages.map(m => m.role).join(', ')}`);

    const response = await fetch(`${QWEN_API_URL}/chat/completions?chat_id=${chatId}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    console.log(`Qwen response status: ${response.status}`);

    if (response.status === 401 || response.status === 403) {
      this.token = null;
      this.activeSession = null;
      throw new QwenSessionExpiredError(
        `Qwen session expired (HTTP ${response.status})`
      );
    }

    if (!response.ok) {
      const text = await response.text();
      console.error(`Qwen error: ${text}`);
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
    let chunkCount = 0;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log(`Stream ended. Total chunks: ${chunkCount}`);
          break;
        }
        chunkCount++;

        const rawChunk = decoder.decode(value, { stream: true });
        buffer += rawChunk;
        
        if (chunkCount <= 2) {
          console.log(`\n=== Raw chunk ${chunkCount} (len=${rawChunk.length}) ===`);
          console.log(rawChunk.substring(0, 500));
          console.log(`=== End chunk ${chunkCount} ===\n`);
        }

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) {
            if (trimmed.length > 0) {
              console.log(`Non-data line: ${trimmed.substring(0, 100)}`);
            }
            continue;
          }

          const dataStr = trimmed.substring(6);
          if (dataStr === "[DONE]") {
            console.log(`Stream [DONE] received`);
            this.updateSession(messages.length, null);
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

              if (chunkCount <= 3) {
                console.log(`Chunk ${chunkCount}: phase=${phase}, text_len=${text.length}, finish=${finish}`);
              }

              if (text && phase === "answer") {
                yield { content: text };
              }
              if (finish) {
                console.log(`Stream finished: ${finish}`);
                this.updateSession(messages.length, null);
                yield { finish };
                return;
              }
            }
          } catch (e) {
            console.log(`Parse error: ${dataStr.substring(0, 100)}`);
            continue;
          }
        }
      }

      console.log(`Stream loop exited normally`);
      if (buffer.length > 0) {
        console.log(`\n=== Remaining buffer (len=${buffer.length}) ===`);
        console.log(buffer.substring(0, 500));
        console.log(`=== End buffer ===\n`);
      }
      this.updateSession(messages.length, null);
      yield { finish: "stop" };
    } finally {
      reader.releaseLock();
    }
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
