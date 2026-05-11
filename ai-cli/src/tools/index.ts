import type { ToolDef, ToolHandler } from "../types.js";
import { readDef, readHandler } from "./read.js";
import { writeDef, writeHandler } from "./write.js";
import { editDef, editHandler } from "./edit.js";
import { grepDef, grepHandler } from "./grep.js";
import { globDef, globHandler } from "./glob.js";
import { bashDef, bashHandler } from "./bash.js";

export interface ToolEntry {
  def: ToolDef;
  handler: ToolHandler;
}

export const tools: ToolEntry[] = [
  { def: readDef, handler: readHandler },
  { def: writeDef, handler: writeHandler },
  { def: editDef, handler: editHandler },
  { def: grepDef, handler: grepHandler },
  { def: globDef, handler: globHandler },
  { def: bashDef, handler: bashHandler },
];

export function getToolDefs(): ToolDef[] {
  return tools.map((t) => t.def);
}

export function getHandler(name: string): ToolHandler | undefined {
  return tools.find((t) => t.def.function.name === name)?.handler;
}
