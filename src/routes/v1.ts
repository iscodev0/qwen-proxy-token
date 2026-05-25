import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { getDb } from "../db";
import { QwenProvider } from "../providers/qwen";
import type { ChatCompletionRequest, QwenCredentials } from "../types";

const v1 = new Hono();

const qwenProvider = new QwenProvider();

v1.post("/auth/qwen", async (c) => {
  const { token } = await c.req.json();

  if (!token) {
    return c.json({ error: "JWT token required" }, 400);
  }

  const credentials: QwenCredentials = { token };
  
  if (!qwenProvider.validateCredentials(credentials)) {
    return c.json({ error: "Invalid or expired JWT token" }, 400);
  }

  const encoded = btoa(JSON.stringify(credentials));

  const db = getDb();
  db.run(
    `INSERT INTO credentials (user_id, provider, encrypted_cookies) 
     VALUES (1, 'qwen_chat', ?)
     ON CONFLICT(user_id, provider) DO UPDATE SET 
       encrypted_cookies = excluded.encrypted_cookies,
       updated_at = datetime('now')`,
    [encoded]
  );

  return c.json({ success: true, message: "Qwen JWT token saved" });
});

v1.get("/models", async (c) => {
  const db = getDb();
  
  const credRow = db
    .query("SELECT encrypted_cookies FROM credentials WHERE user_id = 1 AND provider = 'qwen_chat'")
    .get() as { encrypted_cookies: string } | null;

  if (!credRow) {
    const models = await qwenProvider.listModels();
    return c.json({
      object: "list",
      data: models.map((m) => ({
        id: `qwen/${m.id}`,
        object: "model",
        created: Math.floor(Date.now() / 1000),
        owned_by: m.owned_by,
      })),
    });
  }

  const credentials: QwenCredentials = JSON.parse(atob(credRow.encrypted_cookies));
  const token = await qwenProvider["ensureToken"](credentials);
  const models = await qwenProvider.fetchModels(token);

  return c.json({
    object: "list",
    data: models.map((m) => ({
      id: `qwen/${m.id}`,
      object: "model",
      created: Math.floor(Date.now() / 1000),
      owned_by: m.owned_by,
    })),
  });
});

v1.post("/chat/completions", async (c) => {
  const body: ChatCompletionRequest = await c.req.json();
  
  // Log request details for debugging
  console.log("\n=== Incoming Request ===");
  console.log("Model:", body.model);
  console.log("Messages:", body.messages.length);
  console.log("Stream:", body.stream);
  console.log("Tools:", body.tools ? `${body.tools.length} tools` : "none");
  console.log("Tool choice:", body.tool_choice || "none");
  if (body.tools && body.tools.length > 0) {
    console.log("Tool names:", body.tools.map(t => t.function.name).join(", "));
  }
  console.log("========================\n");

  const db = getDb();
  const credRow = db
    .query("SELECT encrypted_cookies FROM credentials WHERE user_id = 1 AND provider = 'qwen_chat'")
    .get() as { encrypted_cookies: string } | null;

  if (!credRow) {
    return c.json({ error: "Qwen credentials not configured. POST /auth/qwen first." }, 400);
  }

  const credentials: QwenCredentials = JSON.parse(atob(credRow.encrypted_cookies));

  if (body.stream) {
    return streamSSE(c, async (stream) => {
      const chunkId = `chatcmpl-${crypto.randomUUID().substring(0, 12)}`;
      const created = Math.floor(Date.now() / 1000);

      try {
        for await (const chunk of qwenProvider.chatCompletionStream(
          credentials,
          body.model,
          body.messages,
          body.tools,
          body.tool_choice
        )) {
          const sseData = {
            id: chunkId,
            object: "chat.completion.chunk",
            created,
            model: body.model,
            choices: [
              {
                index: 0,
                delta: {
                  ...(chunk.content ? { content: chunk.content } : {}),
                  ...(chunk.toolCalls ? { tool_calls: chunk.toolCalls } : {}),
                },
                finish_reason: chunk.finish || null,
              },
            ],
          };

          await stream.writeSSE({
            data: JSON.stringify(sseData),
            event: "",
          });
        }

        await stream.writeSSE({ data: "[DONE]" });
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        const errorData = {
          error: {
            message: errorMessage,
            type: "api_error",
            code: "provider_error",
          },
        };
        await stream.writeSSE({ data: JSON.stringify(errorData) });
        await stream.writeSSE({ data: "[DONE]" });
      }
    });
  }

  try {
    const result = await qwenProvider.chatCompletion(
      credentials,
      body.model,
      body.messages,
      body.tools,
      body.tool_choice
    );

    return c.json({
      id: result.chatId,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: body.model,
      choices: [
        {
          index: 0,
          message: {
            role: "assistant",
            content: result.content,
            ...(result.toolCalls ? { tool_calls: result.toolCalls } : {}),
          },
          finish_reason: result.toolCalls ? "tool_calls" : "stop",
        },
      ],
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    return c.json(
      {
        error: {
          message: errorMessage,
          type: "api_error",
          code: "provider_error",
        },
      },
      500
    );
  }
});

export { v1 };
