import { chat } from "./api.js";
import { getToolDefs, getHandler } from "./tools/index.js";
import { SYSTEM_PROMPT } from "./prompts.js";
import type { ChatMessage, ToolResult } from "./types.js";

const MAX_TURN = 30;

export async function runAgent(userInput: string, model?: string): Promise<string> {
  const messages: ChatMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: userInput },
  ];

  const toolDefs = getToolDefs();

  for (let turn = 0; turn < MAX_TURN; turn++) {
    const response = await chat(messages, toolDefs, model);
    messages.push(response);

    if (response.content) {
      // We have text content — if no tool calls, we're done
      if (!response.tool_calls || response.tool_calls.length === 0) {
        return response.content;
      }
    }

    if (response.tool_calls && response.tool_calls.length > 0) {
      const toolResults: ToolResult[] = [];

      for (const tc of response.tool_calls) {
        const handler = getHandler(tc.function.name);
        let result: string;

        if (!handler) {
          result = `Error: Unknown tool '${tc.function.name}'`;
        } else {
          try {
            const args = JSON.parse(tc.function.arguments);
            result = await handler(args);
          } catch (err: any) {
            result = `Error executing tool: ${err.message}`;
          }
        }

        toolResults.push({
          tool_call_id: tc.id,
          role: "tool",
          content: result,
        });
      }

      messages.push(...toolResults);
      continue;
    }

    // No content and no tool calls — something went wrong
    return "No response from the model.";
  }

  return "Reached maximum number of tool-using turns. The task may be too complex. Try breaking it down into smaller steps.";
}
