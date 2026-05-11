import { exec } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ToolDef, ToolHandler } from "../types.js";

export const grepDef: ToolDef = {
  type: "function",
  function: {
    name: "Grep",
    description:
      "Search file contents using regex patterns. Returns matching file paths by default. Use output_mode 'content' to see matching lines.",
    parameters: {
      type: "object",
      properties: {
        pattern: {
          type: "string",
          description: "The regex pattern to search for",
        },
        path: {
          type: "string",
          description: "File or directory to search in",
        },
        glob: {
          type: "string",
          description: "Glob pattern to filter files (e.g., '*.ts', '**/*.tsx')",
        },
        output_mode: {
          type: "string",
          enum: ["content", "files_with_matches", "count"],
          description: "Output mode (default: files_with_matches)",
        },
        "-i": {
          type: "boolean",
          description: "Case insensitive search",
        },
        head_limit: {
          type: "integer",
          description: "Limit output to first N lines",
        },
      },
      required: ["pattern"],
    },
  },
};

export const grepHandler: ToolHandler = async (args) => {
  const pattern = args.pattern as string;
  const searchPath = (args.path as string) || ".";
  const glob = args.glob as string | undefined;
  const outputMode = (args.output_mode as string) || "files_with_matches";
  const caseInsensitive = args["-i"] as boolean;
  const headLimit = (args.head_limit as number) || 250;

  const resolvedPath = path.resolve(searchPath);

  try {
    // Try ripgrep first, fall back to Node.js
    const rgCmd = buildRipgrepCmd(pattern, resolvedPath, glob, outputMode, caseInsensitive, headLimit);
    const result = await execAsync(rgCmd, { timeout: 30000 });

    if (!result.stdout.trim()) return "No matches found.";
    return result.stdout.slice(0, 50000);
  } catch (err: any) {
    // If ripgrep not available or error, fall back to manual search
    if (err.code === 1 && !err.stderr) {
      return "No matches found.";
    }

    // Fallback: use Node.js
    try {
      return fallbackGrep(pattern, resolvedPath, glob, outputMode, caseInsensitive, headLimit);
    } catch (fbErr: any) {
      return `Error: ${err.message}`;
    }
  }
};

function buildRipgrepCmd(
  pattern: string,
  dir: string,
  glob?: string,
  outputMode?: string,
  caseInsensitive?: boolean,
  headLimit?: number,
): string {
  const flags: string[] = ["--no-heading", "--color", "never"];

  if (caseInsensitive) flags.push("-i");

  switch (outputMode) {
    case "content":
      flags.push("-n");
      break;
    case "files_with_matches":
      flags.push("-l");
      break;
    case "count":
      flags.push("-c");
      break;
  }

  const globFlags = glob ? `--glob "${glob}"` : "";
  return `rg ${flags.join(" ")} ${globFlags} "${pattern}" "${dir}" | head -n ${headLimit}`;
}

function fallbackGrep(
  pattern: string,
  dir: string,
  glob?: string,
  outputMode?: string,
  caseInsensitive?: boolean,
  headLimit?: number,
): string {
  const regex = new RegExp(pattern, caseInsensitive ? "gi" : "g");
  const results: string[] = [];

  function walkDir(currentDir: string) {
    if (results.length >= headLimit) return;
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      if (results.length >= headLimit) return;
      const fullPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === ".git") continue;
        walkDir(fullPath);
      } else if (entry.isFile()) {
        if (glob && !matchGlob(entry.name, glob)) continue;
        try {
          const content = fs.readFileSync(fullPath, "utf-8");
          const lines = content.split("\n");
          for (let i = 0; i < lines.length; i++) {
            if (results.length >= headLimit) return;
            if (regex.test(lines[i])) {
              regex.lastIndex = 0;
              if (outputMode === "content") {
                results.push(`${fullPath}:${i + 1}:${lines[i]}`);
              } else if (outputMode === "files_with_matches") {
                results.push(fullPath);
                break;
              } else if (outputMode === "count") {
                // handled below
              }
            }
          }
        } catch {
          // skip unreadable files
        }
      }
    }
  }

  walkDir(dir);

  if (outputMode === "count") {
    const counts = new Map<string, number>();
    for (const r of results) {
      const [file] = r.split(":");
      counts.set(file, (counts.get(file) || 0) + 1);
    }
    return [...counts.entries()]
      .map(([f, c]) => `${f}:${c}`)
      .slice(0, headLimit)
      .join("\n");
  }

  return results.slice(0, headLimit).join("\n");
}

function matchGlob(filename: string, glob: string): boolean {
  const regex = new RegExp(
    "^" + glob.replace(/\./g, "\\.").replace(/\*/g, ".*").replace(/\?/g, ".") + "$",
  );
  return regex.test(filename);
}

function execAsync(
  cmd: string,
  opts?: { timeout?: number },
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    exec(cmd, { timeout: opts?.timeout || 120000, maxBuffer: 50 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err && err.code !== 1) reject(err);
      else resolve({ stdout, stderr });
    });
  });
}
