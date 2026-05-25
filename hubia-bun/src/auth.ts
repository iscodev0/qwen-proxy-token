import { createMiddleware } from "hono/factory";
import { getDb } from "./db";
import { verify } from "hono/jwt";

const SECRET_KEY = process.env.SECRET_KEY || "change-me";

export interface AuthUser {
  id: number;
  username: string;
}

export const authMiddleware = createMiddleware<{
  Variables: {
    user: AuthUser;
  };
}>(async (c, next) => {
  const authHeader = c.req.header("Authorization");

  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return c.json({ error: "Missing or invalid Authorization header" }, 401);
  }

  const token = authHeader.substring(7);

  try {
    const payload = await verify(token, SECRET_KEY, "HS256");
    
    const db = getDb();
    const user = db
      .query("SELECT id, username FROM users WHERE id = ?")
      .get(payload.sub as number) as { id: number; username: string } | null;

    if (!user) {
      return c.json({ error: "User not found" }, 401);
    }

    c.set("user", user);
    await next();
  } catch (error) {
    return c.json({ error: "Invalid token" }, 401);
  }
});
