import * as readline from "node:readline";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import chalk from "chalk";
import { initApi } from "./api.js";
import { runAgent } from "./agent.js";

const CONFIG_DIR = path.join(os.homedir(), ".ai-cli");
const CONFIG_FILE = path.join(CONFIG_DIR, "config.json");

interface Config {
  apiKey?: string;
  baseUrl?: string;
  model?: string;
}

function loadConfig(): Config {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      return JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8"));
    }
  } catch {
    // ignore
  }
  return {};
}

function saveConfig(config: Config): void {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2), "utf-8");
}

function parseArgs(argv: string[]): {
  printMode: boolean;
  prompt: string;
  model?: string;
} {
  const args = argv.slice(2);
  let printMode = false;
  let prompt = "";
  let model: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "-p" || a === "--print") {
      printMode = true;
      if (args[i + 1] != null && !args[i + 1].startsWith("-")) {
        prompt = args[i + 1];
        i++;
      }
    } else if (a === "-m" || a === "--model") {
      model = args[i + 1];
      i++;
    } else if (a === "-h" || a === "--help") {
      console.log(`
  AI-CLI — AI Programming Assistant powered by DeepSeek

  Usage:
    ai-cli                  Interactive REPL mode
    ai-cli -p "prompt"      One-shot print mode (non-interactive)
    ai-cli -m <model> -p "prompt"   Use specific model

  Options:
    -p, --print <prompt>    Run a single prompt and exit
    -m, --model <name>      Model to use (default: deepseek-chat)
    -h, --help              Show this help

  Environment:
    DEEPSEEK_API_KEY        Your DeepSeek API key
    DEEPSEEK_BASE_URL       API base URL (default: https://api.deepseek.com)

  Config: ${CONFIG_FILE}
`);
      process.exit(0);
    } else if (!a.startsWith("-") && !prompt && !printMode) {
      // Positional prompt (for convenience: ai-cli "your question")
      prompt = a;
      printMode = true;
    }
  }

  return { printMode, prompt, model };
}

async function ensureApiKey(config: Config): Promise<{ apiKey: string; config: Config }> {
  let apiKey = process.env.DEEPSEEK_API_KEY || config.apiKey;

  if (!apiKey) {
    if (process.stdin.isTTY) {
      console.log(chalk.yellow("  DeepSeek API Key not found."));
      console.log(chalk.dim("  Get one at: https://platform.deepseek.com/api_keys\n"));

      const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
      apiKey = await new Promise<string>((resolve) => {
        rl.question(chalk.white("  Enter your DeepSeek API Key: "), (answer) => {
          rl.close();
          resolve(answer.trim());
        });
      });

      if (!apiKey) {
        console.log(chalk.red("\n  No API key provided. Exiting.\n"));
        process.exit(1);
      }

      config.apiKey = apiKey;
      saveConfig(config);
      console.log(chalk.green("  API Key saved to ~/.ai-cli/config.json\n"));
    } else {
      console.log(chalk.red("  DEEPSEEK_API_KEY environment variable not set."));
      console.log(chalk.dim("  Set it with: $env:DEEPSEEK_API_KEY=\"sk-...\" (PowerShell)"));
      console.log(chalk.dim("  Or run interactively to save it to config.\n"));
      process.exit(1);
    }
  }

  return { apiKey, config };
}

async function repl(apiKey: string, baseUrl: string, model: string): Promise<void> {
  console.log(chalk.dim(`  Model: ${model}  |  Base URL: ${baseUrl}`));
  console.log(chalk.dim("  Type /help for commands, /exit to quit\n"));

  initApi(apiKey, baseUrl);

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: chalk.green("\n> "),
  });

  rl.prompt();

  for await (const line of rl) {
    const input = line.trim();

    if (!input) {
      rl.prompt();
      continue;
    }

    if (input.startsWith("/")) {
      const cmd = input.toLowerCase();

      if (cmd === "/exit" || cmd === "/quit") {
        console.log(chalk.dim("\n  Goodbye!\n"));
        process.exit(0);
      }

      if (cmd === "/help") {
        console.log(chalk.cyan("\n  Commands:"));
        console.log("  /exit, /quit  — Exit");
        console.log("  /help         — Show this help");
        console.log("  /clear        — Clear screen");
        console.log("  /config       — Show configuration");
        console.log("  /model <name> — Change model");
        console.log("  /key <apikey> — Update API key\n");
        rl.prompt();
        continue;
      }

      if (cmd === "/clear") {
        console.clear();
        rl.prompt();
        continue;
      }

      if (cmd === "/config") {
        console.log(chalk.cyan("\n  Configuration:"));
        console.log(`  Config:  ${CONFIG_FILE}`);
        console.log(`  API Key: ${apiKey.slice(0, 8)}***`);
        console.log(`  Base URL: ${baseUrl}`);
        console.log(`  Model:   ${model}\n`);
        rl.prompt();
        continue;
      }

      console.log(chalk.red(`\n  Unknown: ${input}\n`));
      rl.prompt();
      continue;
    }

    console.log(chalk.dim("\n  Thinking..."));
    try {
      const result = await runAgent(input, model);
      console.log(chalk.white("\n" + result + "\n"));
    } catch (err: any) {
      console.log(chalk.red(`\n  Error: ${err.message}\n`));
    }

    rl.prompt();
  }
}

async function printMode(prompt: string, apiKey: string, baseUrl: string, model: string): Promise<void> {
  initApi(apiKey, baseUrl);
  try {
    const result = await runAgent(prompt, model);
    console.log(result);
  } catch (err: any) {
    console.error(chalk.red(`Error: ${err.message}`));
    process.exit(1);
  }
}

async function main(): Promise<void> {
  const { printMode: isPrint, prompt, model: cliModel } = parseArgs(process.argv);

  let config = loadConfig();
  const { apiKey, config: updatedConfig } = await ensureApiKey(config);
  config = updatedConfig;

  const baseUrl = process.env.DEEPSEEK_BASE_URL || config.baseUrl || "https://api.deepseek.com";
  const model = cliModel || process.env.DEEPSEEK_MODEL || config.model || "deepseek-chat";

  if (isPrint && prompt) {
    await printMode(prompt, apiKey, baseUrl, model);
  } else if (isPrint) {
    // Read from stdin
    const chunks: string[] = [];
    process.stdin.setEncoding("utf-8");
    for await (const chunk of process.stdin) {
      chunks.push(chunk as string);
    }
    await printMode(chunks.join("").trim() || "Hello!", apiKey, baseUrl, model);
  } else {
    console.log(chalk.cyan("\n  AI-CLI — AI Programming Assistant"));
    console.log(chalk.dim("  Powered by DeepSeek\n"));
    await repl(apiKey, baseUrl, model);
  }
}

main().catch((err) => {
  console.error(chalk.red(`Fatal: ${err.message}`));
  process.exit(1);
});
