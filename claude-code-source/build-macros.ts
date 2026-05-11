// Build-time macro shims for Claude Code source
// In Bun build, these are inlined at compile time.
// At runtime, we provide sensible defaults.

// MACRO — build-time value injection
(globalThis as any).MACRO = {
  VERSION: '2.1.88',
  BUILD_TIME: new Date().toISOString(),
  COMMIT_HASH: 'unknown',
};

// bun:bundle — feature flag system
// Resolved at build time in production. At runtime, read from env vars.
const _featureCache = new Map<string, boolean>();

(globalThis as any).bun = {
  ...((globalThis as any).bun || {}),
  bundle: {
    feature(name: string): boolean {
      if (_featureCache.has(name)) return _featureCache.get(name)!;
      const envKey = `CLAUDE_CODE_FEATURE_${name}`;
      const val = process.env[envKey];
      // Default: external build — all internal features disabled
      const defaults: Record<string, boolean> = {
        'BUDDY': false,
        'KAIROS': false,
        'VOICE_MODE': false,
        'COORDINATOR_MODE': false,
        'BRIDGE_MODE': false,
        'DAEMON': false,
        'FORK_SUBAGENT': false,
        'TORCH': false,
        'ULTRAPLAN': false,
        'CHICAGO_MCP': false,
        'BG_SESSIONS': false,
        'TEMPLATES': false,
        'SELF_HOSTED_RUNNER': false,
        'BYOC_ENVIRONMENT_RUNNER': false,
        'WEB_BROWSER_TOOL': false,
        'ABLATION_BASELINE': false,
        'DUMP_SYSTEM_PROMPT': false,
      };
      const enabled = val === '1' || val === 'true' || defaults[name] === true;
      _featureCache.set(name, enabled);
      return enabled;
    },
  },
};

console.log('[build-macros] Initialized: MACRO + bun:bundle shim');
