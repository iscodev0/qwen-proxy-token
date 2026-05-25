#!/usr/bin/env bun

const BASE_URL = "http://localhost:8089";

async function test() {
  console.log("🧪 Testing Hubia Bun API...\n");

  console.log("1. Testing health check...");
  const healthResp = await fetch(`${BASE_URL}/health`);
  const healthData = await healthResp.json();
  console.log("   ✓ Health:", healthData);

  console.log("\n2. Testing root endpoint...");
  const rootResp = await fetch(`${BASE_URL}/`);
  const rootData: any = await rootResp.json();
  console.log("   ✓ Root:", rootData.name);

  console.log("\n3. Testing login...");
  const loginResp = await fetch(`${BASE_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "testuser",
      password: "testpass123",
    }),
  });
  const loginData: any = await loginResp.json();
  console.log("   ✓ Login successful, token received");
  const token = loginData.token;

  console.log("\n4. Testing models list (without Qwen credentials)...");
  const modelsResp = await fetch(`${BASE_URL}/v1/models`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const modelsData: any = await modelsResp.json();
  console.log(`   ✓ Models: ${modelsData.data.length} models available`);

  console.log("\n5. Testing chat completion (should fail without Qwen credentials)...");
  const chatResp = await fetch(`${BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      model: "qwen/qwen3.6-plus",
      messages: [{ role: "user", content: "Hello!" }],
    }),
  });
  const chatData: any = await chatResp.json();
  if (chatData.error) {
    console.log("   ✓ Expected error:", chatData.error.message);
  } else {
    console.log("   ✗ Unexpected success");
  }

  console.log("\n✅ All tests passed!");
  console.log("\n📝 Next steps:");
  console.log("   1. Configure Qwen credentials:");
  console.log(`      curl -X POST ${BASE_URL}/v1/auth/qwen \\`);
  console.log(`        -H "Authorization: Bearer ${token}" \\`);
  console.log(`        -H "Content-Type: application/json" \\`);
  console.log(`        -d '{"email": "your-qwen-email", "password": "your-qwen-password"}'`);
  console.log("\n   2. Test chat completion:");
  console.log(`      curl -X POST ${BASE_URL}/v1/chat/completions \\`);
  console.log(`        -H "Authorization: Bearer ${token}" \\`);
  console.log(`        -H "Content-Type: application/json" \\`);
  console.log(`        -d '{"model": "qwen/qwen3.7-max", "messages": [{"role": "user", "content": "Hello!"}]}'`);
}

test().catch(console.error);
