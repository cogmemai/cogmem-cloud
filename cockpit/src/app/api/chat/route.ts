import { createOpenAI } from "@ai-sdk/openai";
import { convertToModelMessages, streamText } from "ai";
import { cookies } from "next/headers";

export const maxDuration = 30;

// Server-side only — route through backend for LLM + KOS ingestion
const BACKEND_URL =
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "https://api.cogmem.ai";

export async function POST(req: Request) {
  const cookieStore = await cookies();
  const token = cookieStore.get("cogmem_token");
  if (!token?.value) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Point the AI SDK at the backend's OpenAI-compatible endpoint.
  // The backend proxies to OpenRouter AND triggers KOS ingestion.
  const backend = createOpenAI({
    apiKey: "unused",
    baseURL: `${BACKEND_URL}/api/v1/chat/v1`,
    headers: {
      Authorization: `Bearer ${token.value}`,
    },
  });

  const { messages } = await req.json();
  const modelMessages = await convertToModelMessages(messages);

  const result = streamText({
    model: backend("openai/gpt-4o-mini"),
    messages: modelMessages,
  });

  return result.toUIMessageStreamResponse();
}
