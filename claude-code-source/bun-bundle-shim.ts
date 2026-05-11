// Shim for 'bun:bundle' — provides feature() at runtime
// In Bun build, feature('NAME') is a macro resolved at build time.
// At runtime, we read from env vars: CLAUDE_CODE_FEATURE_<NAME>=1

const featureCache = new Map<string, boolean>();

export function feature(name: string): boolean {
  if (featureCache.has(name)) return featureCache.get(name)!;
  const envKey = `CLAUDE_CODE_FEATURE_${name}`;
  const val = process.env[envKey];
  const enabled = val === '1' || val === 'true';
  featureCache.set(name, enabled);
  return enabled;
}
