import { exec, execSync } from "node:child_process";
import * as os from "node:os";
import type { ToolDef, ToolHandler } from "../types.js";

const isWindows = os.platform() === "win32";

export const bashDef: ToolDef = {
  type: "function",
  function: {
    name: "Bash",
    description:
      "Execute a shell command. Use for git operations, package management, file operations, and running scripts. Commands run with a timeout of 2 minutes.",
    parameters: {
      type: "object",
      properties: {
        command: {
          type: "string",
          description: "The shell command to execute",
        },
        description: {
          type: "string",
          description: "Brief description of what this command does",
        },
        timeout: {
          type: "integer",
          description: "Timeout in milliseconds (default: 120000, max: 600000)",
        },
      },
      required: ["command"],
    },
  },
};

export const bashHandler: ToolHandler = async (args) => {
  const command = args.command as string;
  const timeout = (args.timeout as number) || 120000;

  try {
    const result = await execAsync(command, {
      timeout: Math.min(timeout, 600000),
      maxBuffer: 10 * 1024 * 1024,
      shell: isWindows ? "powershell.exe" : "/bin/bash",
    });

    let output = "";
    if (result.stdout) output += result.stdout;
    if (result.stderr) output += (output ? "\n" : "") + "[stderr]\n" + result.stderr;

    if (!output.trim()) return "(no output)";
    return output.slice(0, 50000);
  } catch (err: any) {
    let msg = `Error: ${err.message}`;
    if (err.stdout) msg += "\n\n[stdout]\n" + err.stdout;
    if (err.stderr) msg += "\n\n[stderr]\n" + err.stderr;
    if (err.killed) msg += "\n\n(Command timed out)";
    return msg;
  }
};

function execAsync(
  cmd: string,
  opts: { timeout: number; maxBuffer: number; shell: string },
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    exec(cmd, opts, (err, stdout, stderr) => {
      if (err) {
        (err as any).stdout = stdout;
        (err as any).stderr = stderr;
        reject(err);
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
}
