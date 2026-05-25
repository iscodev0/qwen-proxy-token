import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { sign } from "hono/jwt";
import { getDb } from "../db";
import { authMiddleware } from "../auth";
import { QwenProvider } from "../providers/qwen";
import type { ChatCompletionRequest, QwenCredentials } from "../types";

const SECRET_KEY = process.env.SECRET_KEY || "change-me";
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY || "change-me-encryption";

const v1 = new Hono();

const qwenProvider = new QwenProvider();

v1.post("/auth/login", async (c) => {
  const { username, password } = await c.req.json();

  if (!username || !password) {
    return c.json({ error: "Username and password required" }, 400);
  }

  const db = getDb();
  const user = db
    .query("SELECT id, username, password_hash FROM users WHERE username = ?")
    .get(username) as { id: number; username: string; password_hash: string } | null;

  if (!user) {
    const hash = await Bun.password.hash(password);
    db.run("INSERT INTO users (username, password_hash) VALUES (?, ?)", [username, hash]);
    
    const newUser = db
      .query("SELECT id, username FROM users WHERE username = ?")
      .get(username) as { id: number; username: string };

    const token = await sign({ sub: newUser.id, username: newUser.username }, SECRET_KEY);
    return c.json({ token, user: { id: newUser.id, username: newUser.username } });
  }

  const valid = await Bun.password.verify(password, user.password_hash);
  if (!valid) {
    return c.json({ error: "Invalid credentials" }, 401);
  }

  const token = await sign({ sub: user.id, username: user.username }, SECRET_KEY);
  return c.json({ token, user: { id: user.id, username: user.username } });
});

v1.post("/auth/qwen", authMiddleware, async (c) => {
  const user = c.get("user");
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
     VALUES (?, 'qwen_chat', ?)
     ON CONFLICT(user_id, provider) DO UPDATE SET 
       encrypted_cookies = excluded.encrypted_cookies,
       updated_at = datetime('now')`,
    [user.id, encoded]
  );

  return c.json({ success: true, message: "Qwen JWT token saved" });
});

v1.get("/models", authMiddleware, async (c) => {
  const user = c.get("user");
  const db = getDb();
  
  const credRow = db
    .query("SELECT encrypted_cookies FROM credentials WHERE user_id = ? AND provider = 'qwen_chat'")
    .get(user.id) as { encrypted_cookies: string } | null;

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

v1.post("/chat/completions", authMiddleware, async (c) => {
  const user = c.get("user");
  const body: ChatCompletionRequest = await c.req.json();

  const db = getDb();
  const credRow = db
    .query("SELECT encrypted_cookies FROM credentials WHERE user_id = ? AND provider = 'qwen_chat'")
    .get(user.id) as { encrypted_cookies: string } | null;

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
          body.messages
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
      body.messages
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
          },
          finish_reason: "stop",
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
