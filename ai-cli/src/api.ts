import OpenAI from "openai";
import type { ChatMessage, ToolDef } from "./types.js";

let client: OpenAI | null = null;

export function initApi(apiKey: string, baseUrl?: string): OpenAI {
  client = new OpenAI({
    apiKey,
    baseURL: baseUrl || "https://api.deepseek.com",
  });
  return client;
}

export function getClient(): OpenAI {
  if (!client) throw new Error("API not initialized. Call initApi() first.");
  return client;
}

export async function chat(
  messages: ChatMessage[],
  tools: ToolDef[],
  model: string = "deepseek-chat",
): Promise<ChatMessage> {
  const c = getClient();

  const response = await c.chat.completions.create({
    model,
    messages: messages as OpenAI.Chat.Completions.ChatCompletionMessageParam[],
    tools: tools as OpenAI.Chat.Completions.ChatCompletionTool[],
    tool_choice: "auto",
    temperature: 0.3,
  });

  const choice = response.choices[0];
  if (!choice) throw new Error("No response from API");

  const msg = choice.message;

  const result: ChatMessage = {
    role: "assistant",
    content: msg.content || null,
  };

  if (msg.tool_calls && msg.tool_calls.length > 0) {
    result.tool_calls = msg.tool_calls.map((tc) => ({
      id: tc.id,
      type: "function" as const,
      function: {
        name: tc.function.name,
        arguments: tc.function.arguments,
      },
    }));
  }

  return result;
}
