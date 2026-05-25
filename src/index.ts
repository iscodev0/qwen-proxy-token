import { Hono } from "hono";
import { cors } from "hono/cors";
import { serveStatic } from "hono/bun";
import { v1 } from "./routes/v1";
import { closeDb } from "./db";

const app = new Hono();

app.use(
  "/*",
  cors({
    origin: "*",
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type", "Authorization"],
  })
);

app.use("/public/*", serveStatic({ root: "./" }));

app.get("/", serveStatic({ path: "./public/index.html" }));

app.get("/health", (c) => {
  return c.json({ status: "ok", timestamp: new Date().toISOString() });
});

app.route("/v1", v1);

app.notFound((c) => {
  return c.json({ error: "Not found" }, 404);
});

app.onError((err, c) => {
  console.error("Unhandled error:", err);
  return c.json(
    {
      error: {
        message: "Internal server error",
        type: "server_error",
      },
    },
    500
  );
});

const port = parseInt(process.env.PORT || "8089");
const host = process.env.HOST || "0.0.0.0";

console.log(`🚀 Hubia Qwen Proxy starting on http://${host}:${port}`);
console.log(`📚 API docs: http://${host}:${port}/`);
console.log(`❤️  Health check: http://${host}:${port}/health`);

process.on("SIGINT", () => {
  console.log("\nShutting down...");
  closeDb();
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("\nShutting down...");
  closeDb();
  process.exit(0);
});

export default {
  port,
  hostname: host,
  fetch: app.fetch,
  idleTimeout: 120,
};
