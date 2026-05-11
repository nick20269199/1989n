import * as fs from "node:fs";
import * as path from "node:path";
import type { ToolDef, ToolHandler } from "../types.js";

export const globDef: ToolDef = {
  type: "function",
  function: {
    name: "Glob",
    description:
      "Find files matching a glob pattern. Returns file paths sorted by modification time.",
    parameters: {
      type: "object",
      properties: {
        pattern: {
          type: "string",
          description: "The glob pattern to match (e.g., '**/*.ts', 'src/**/*.tsx')",
        },
        path: {
          type: "string",
          description: "The directory to search in (defaults to current working directory)",
        },
      },
      required: ["pattern"],
    },
  },
};

export const globHandler: ToolHandler = async (args) => {
  const pattern = args.pattern as string;
  const searchPath = (args.path as string) || process.cwd();

  const resolved = path.resolve(searchPath);

  try {
    const results = globSearch(resolved, pattern);
    if (results.length === 0) return "No files found.";

    // Sort by modification time
    const withStats = results.map((f) => {
      try {
        const stat = fs.statSync(f);
        return { path: f, mtime: stat.mtimeMs };
      } catch {
        return { path: f, mtime: 0 };
      }
    });

    withStats.sort((a, b) => b.mtime - a.mtime);

    const lines = withStats.map((f, i) => `${i + 1}. ${f.path}`);
    return lines.slice(0, 200).join("\n");
  } catch (err: any) {
    return `Error searching files: ${err.message}`;
  }
};

function globSearch(rootDir: string, pattern: string): string[] {
  const results: string[] = [];
  const parts = pattern.replace(/\\/g, "/");

  // Convert glob to regex
  const regex = globToRegex(parts);

  function walk(dir: string) {
    if (results.length >= 500) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (results.length >= 500) return;
      const fullPath = path.join(dir, entry.name);
      const relativePath = path.relative(rootDir, fullPath).replace(/\\/g, "/");

      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === ".git") continue;
        // Check if this directory could match (for ** patterns)
        const dirPart = relativePath + "/";
        if (regex.partial(dirPart)) {
          walk(fullPath);
        }
      } else if (entry.isFile()) {
        if (regex.test(relativePath)) {
          results.push(fullPath);
        }
      }
    }
  }

  // If pattern starts with **, search from root
  // Otherwise, try to find the base directory
  const baseMatch = parts.match(/^([^*?\[\]{}]+)\//);
  const baseDir = baseMatch ? path.join(rootDir, baseMatch[1]) : rootDir;

  if (fs.existsSync(baseDir)) {
    walk(rootDir);
  }

  return results;
}

function globToRegex(pattern: string): {
  test: (s: string) => boolean;
  partial: (s: string) => boolean;
} {
  let regexStr = "^";
  let i = 0;
  while (i < pattern.length) {
    if (pattern[i] === "*" && pattern[i + 1] === "*") {
      // ** — match any path segment
      if (pattern[i + 2] === "/") {
        regexStr += "(?:.+/)?";
        i += 3;
      } else if (i + 2 >= pattern.length) {
        regexStr += ".*";
        i += 2;
      } else {
        regexStr += "[^/]*";
        i += 1;
      }
    } else if (pattern[i] === "*") {
      regexStr += "[^/]*";
      i += 1;
    } else if (pattern[i] === "?") {
      regexStr += "[^/]";
      i += 1;
    } else if (pattern[i] === ".") {
      regexStr += "\\.";
      i += 1;
    } else if (pattern[i] === "{") {
      const end = pattern.indexOf("}", i);
      if (end !== -1) {
        const options = pattern.slice(i + 1, end).split(",");
        regexStr += "(" + options.join("|") + ")";
        i = end + 1;
      } else {
        regexStr += "\\{";
        i += 1;
      }
    } else {
      regexStr += pattern[i];
      i += 1;
    }
  }
  regexStr += "$";

  const regex = new RegExp(regexStr);
  return {
    test: (s: string) => regex.test(s),
    partial: (s: string) => {
      const partialPattern = "^" + regexStr.slice(1).replace(/\$/, "");
      return new RegExp(partialPattern).test(s);
    },
  };
}
