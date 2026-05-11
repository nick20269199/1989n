import * as fs from "node:fs";
import * as path from "node:path";
import type { ToolDef, ToolHandler } from "../types.js";

export const writeDef: ToolDef = {
  type: "function",
  function: {
    name: "Write",
    description:
      "Write content to a file. Creates parent directories if needed. Overwrites existing files.",
    parameters: {
      type: "object",
      properties: {
        file_path: {
          type: "string",
          description: "Absolute path to the file to write",
        },
        content: {
          type: "string",
          description: "The content to write to the file",
        },
      },
      required: ["file_path", "content"],
    },
  },
};

export const writeHandler: ToolHandler = async (args) => {
  const filePath = args.file_path as string;
  const content = args.content as string;

  const resolved = path.resolve(filePath);

  try {
    const dir = path.dirname(resolved);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    const existed = fs.existsSync(resolved);
    fs.writeFileSync(resolved, content, "utf-8");

    const size = Buffer.byteLength(content, "utf-8");
    const prefix = existed ? "Updated" : "Created";
    return `${prefix} file: ${resolved} (${size} bytes)`;
  } catch (err: any) {
    return `Error writing file: ${err.message}`;
  }
};
