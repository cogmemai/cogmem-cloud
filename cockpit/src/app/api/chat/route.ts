import { createOpenAI } from "@ai-sdk/openai";
import { convertToModelMessages, streamText } from "ai";
import { cookies } from "next/headers";

export const maxDuration = 30;

// Server-side only — use internal K8s service URL in production
const API_URL = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://api.cogmem.ai";

const openrouter = createOpenAI({
  apiKey: process.env.OPENROUTER_API_KEY ?? "",
  baseURL: "https://openrouter.ai/api/v1",
});

export async function POST(req: Request) {
  const cookieStore = await cookies();
  const token = cookieStore.get("cogmem_token");
  if (!token?.value) {
    return new Response("Unauthorized", { status: 401 });
  }

  const { messages } = await req.json();
  const modelMessages = await convertToModelMessages(messages);

  const result = streamText({
    model: openrouter("openai/gpt-4o-mini"),
    messages: modelMessages,
    async onFinish({ text }) {
      // Find the last user message to ingest along with the assistant response
      const lastUserMsg = [...messages]
        .reverse()
        .find((m: { role: string }) => m.role === "user");
      const userContent =
        lastUserMsg?.content?.[0]?.text ?? lastUserMsg?.content ?? "";

      if (!userContent || !text) return;

      // Fire-and-forget: send both messages to the backend KOS ingestion endpoint
      fetch(`${API_URL}/api/v1/kos/ingest`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token!.value}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_message: userContent,
          assistant_message: text,
        }),
      }).catch(() => {
        // Ingestion failure should not affect the chat experience
      });
    },
  });

  return result.toUIMessageStreamResponse();
}
