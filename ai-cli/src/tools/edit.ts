import * as fs from "node:fs";
import * as path from "node:path";
import type { ToolDef, ToolHandler } from "../types.js";

export const editDef: ToolDef = {
  type: "function",
  function: {
    name: "Edit",
    description:
      "Perform exact string replacement in a file. The old_string must match exactly one location in the file. Use replace_all to replace all occurrences.",
    parameters: {
      type: "object",
      properties: {
        file_path: {
          type: "string",
          description: "Absolute path to the file to edit",
        },
        old_string: {
          type: "string",
          description: "The exact text to find and replace",
        },
        new_string: {
          type: "string",
          description: "The text to replace it with",
        },
        replace_all: {
          type: "boolean",
          description: "Replace all occurrences (default: false)",
        },
      },
      required: ["file_path", "old_string", "new_string"],
    },
  },
};

export const editHandler: ToolHandler = async (args) => {
  const filePath = args.file_path as string;
  const oldStr = args.old_string as string;
  const newStr = args.new_string as string;
  const replaceAll = args.replace_all as boolean;

  const resolved = path.resolve(filePath);

  try {
    const content = fs.readFileSync(resolved, "utf-8");

    if (replaceAll) {
      if (!content.includes(oldStr)) {
        return `Error: old_string not found in file.`;
      }
      const newContent = content.split(oldStr).join(newStr);
      fs.writeFileSync(resolved, newContent, "utf-8");
      const count = content.split(oldStr).length - 1;
      return `Replaced ${count} occurrence(s) in ${resolved}`;
    }

    const firstIndex = content.indexOf(oldStr);
    if (firstIndex === -1) {
      return `Error: old_string not found in file.`;
    }

    const secondIndex = content.indexOf(oldStr, firstIndex + 1);
    if (secondIndex !== -1) {
      return `Error: old_string is not unique in file. Found at positions ${firstIndex} and ${secondIndex}. Use replace_all or provide more context to make it unique.`;
    }

    const newContent =
      content.slice(0, firstIndex) + newStr + content.slice(firstIndex + oldStr.length);
    fs.writeFileSync(resolved, newContent, "utf-8");
    return `Edited ${resolved} — 1 replacement made.`;
  } catch (err: any) {
    if (err.code === "ENOENT") {
      return `Error: File not found: ${resolved}`;
    }
    return `Error editing file: ${err.message}`;
  }
};
