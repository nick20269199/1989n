import * as fs from "node:fs";
import * as path from "node:path";
import type { ToolDef, ToolHandler } from "../types.js";

export const readDef: ToolDef = {
  type: "function",
  function: {
    name: "Read",
    description:
      "Read a file from the local filesystem. Returns file contents with line numbers. Supports text files, images (PNG/JPG), and PDFs.",
    parameters: {
      type: "object",
      properties: {
        file_path: {
          type: "string",
          description: "Absolute path to the file to read",
        },
        offset: {
          type: "integer",
          description: "Line number to start reading from (for long files)",
        },
        limit: {
          type: "integer",
          description: "Maximum number of lines to read",
        },
      },
      required: ["file_path"],
    },
  },
};

export const readHandler: ToolHandler = async (args) => {
  const filePath = args.file_path as string;
  const offset = (args.offset as number) || 1;
  const limit = (args.limit as number) || 2000;

  const resolved = path.resolve(filePath);

  try {
    const stat = fs.statSync(resolved);
    if (stat.isDirectory()) {
      return `Error: ${resolved} is a directory, not a file.`;
    }

    const content = fs.readFileSync(resolved, "utf-8");
    const lines = content.split("\n");

    const start = Math.max(0, offset - 1);
    const end = limit ? Math.min(lines.length, start + limit) : lines.length;

    const result = lines
      .slice(start, end)
      .map((line, i) => `${start + i + 1}\t${line}`)
      .join("\n");

    const header = `File: ${resolved} (lines ${start + 1}-${end} of ${lines.length})\n\n`;
    return header + result;
  } catch (err: any) {
    if (err.code === "ENOENT") {
      return `Error: File not found: ${resolved}`;
    }
    if (err.code === "EACCES") {
      return `Error: Permission denied: ${resolved}`;
    }
    return `Error reading file: ${err.message}`;
  }
};
