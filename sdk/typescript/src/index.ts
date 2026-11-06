/**
 * @verano/sdk: fetch the prompt Verano serves for a label, with a local cache and a safe fallback.
 *
 * Each call asks Verano for the prompt a label points at, sending the saved copy's ETag so an unchanged prompt costs an
 * empty 304 answer. The last good copy is kept in memory and, where a file system exists (Node, Bun, Deno), on disk.
 * If Verano cannot be reached (no connection, a timeout, a server error) the saved copy is returned with
 * `fromCache: true` and `onFallback` is called, so an outage never takes the app down. A "no" from Verano (a revoked
 * token, an unknown label) is thrown as `VeranoRefused` and never hidden behind the cache. No dependencies: only `fetch`.
 */

export const VERSION = "0.1.0";

const API_PREFIX = "/api/v1";
const PLACEHOLDER = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

export interface Prompt {
  name: string;
  label: string | null;
  version: number;
  versionId: string;
  systemTemplate: string | null;
  userTemplate: string | null;
  variables: string[];
  defaultParams: Record<string, unknown>;
  updatedAt: string;
  /** True when Verano could not be reached and this is the last good saved copy. */
  fromCache: boolean;
}

export interface VeranoOptions {
  baseUrl?: string;
  token?: string;
  projectId?: string;
  /** Folder for the on-disk copy. Defaults to the user's cache folder; pass `null` to keep copies in memory only. */
  cacheDir?: string | null;
  /** Milliseconds to wait for Verano. Default 3000. */
  timeoutMs?: number;
  /** Milliseconds to skip asking Verano again after a fresh answer. Default 0 (always revalidate). */
  maxAgeMs?: number;
  /** Called when the saved copy is used because Verano could not be reached. */
  onFallback?: (message: string, prompt: Prompt) => void;
  /** A replacement for the global `fetch` (tests, proxies). */
  fetch?: typeof fetch;
}

export class VeranoError extends Error {}

/** Verano could not be reached and there is no saved copy to fall back on. */
export class VeranoUnreachable extends VeranoError {}

/** Verano answered but said no: a wrong or revoked token, an unknown prompt or label. */
export class VeranoRefused extends VeranoError {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

interface Wire {
  name: string;
  label: string | null;
  version: number;
  version_id: string;
  system_template: string | null;
  user_template: string | null;
  variables: string[];
  default_params: Record<string, unknown>;
  updated_at: string;
}

interface Saved {
  etag: string | null;
  prompt: Prompt;
}

/** Fills `{{ name }}` placeholders; it does not run template logic. Every placeholder needs a value. */
export function render(
  prompt: Prompt,
  values: Record<string, unknown>,
): { system: string | null; user: string | null } {
  const missing = prompt.variables.filter((name) => !(name in values));
  if (missing.length > 0) throw new VeranoError(`Missing values for: ${missing.join(", ")}.`);
  const fill = (text: string | null) =>
    text === null ? null : text.replace(PLACEHOLDER, (_, name: string) => String(values[name]));
  return { system: fill(prompt.systemTemplate), user: fill(prompt.userTemplate) };
}

function fromWire(data: Wire, fromCache: boolean): Prompt {
  return {
    name: data.name,
    label: data.label ?? null,
    version: data.version,
    versionId: data.version_id,
    systemTemplate: data.system_template ?? null,
    userTemplate: data.user_template ?? null,
    variables: data.variables ?? [],
    defaultParams: data.default_params ?? {},
    updatedAt: data.updated_at ?? "",
    fromCache,
  };
}

function env(name: string): string | undefined {
  const scope = globalThis as { process?: { env?: Record<string, string | undefined> } };
  return scope.process?.env?.[name];
}

async function digest(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash))
    .slice(0, 16)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export class Verano {
  private readonly base: string;
  private readonly token: string;
  private readonly project: string;
  private readonly cacheDir: string | null;
  private readonly timeoutMs: number;
  private readonly maxAgeMs: number;
  private readonly onFallback?: (message: string, prompt: Prompt) => void;
  private readonly doFetch: typeof fetch;
  private readonly memory = new Map<string, { at: number; saved: Saved }>();

  constructor(options: VeranoOptions = {}) {
    const url = options.baseUrl ?? env("VERANO_URL");
    const token = options.token ?? env("VERANO_API_TOKEN");
    const project = options.projectId ?? env("VERANO_PROJECT_ID");
    if (!url || !token || !project) {
      throw new VeranoError(
        "Give the server address, a token and the project id, or set VERANO_URL, VERANO_API_TOKEN and " +
          "VERANO_PROJECT_ID. Make a read-only token with `verano token create --read-only`.",
      );
    }
    this.base = url.replace(/\/+$/, "").replace(new RegExp(`${API_PREFIX}$`), "");
    this.token = token;
    this.project = project;
    this.cacheDir = options.cacheDir === undefined ? null : options.cacheDir;
    this.timeoutMs = options.timeoutMs ?? 3000;
    this.maxAgeMs = options.maxAgeMs ?? 0;
    this.onFallback = options.onFallback;
    this.doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  /** The prompt `label` points at; a given `version`; or, with `label: null`, the latest saved version. */
  async prompt(
    name: string,
    options: { label?: string | null; version?: number } = {},
  ): Promise<Prompt> {
    const version = options.version;
    const label =
      version !== undefined ? null : options.label === undefined ? "production" : options.label;
    const key = await digest(`${this.base}|${this.project}|${name}|${label}|${version}`);
    const hit = this.memory.get(key);
    if (hit && this.maxAgeMs > 0 && Date.now() - hit.at < this.maxAgeMs) return hit.saved.prompt;
    const saved = hit?.saved ?? (await this.readDisk(key));
    try {
      const fresh = await this.fetchPrompt(name, label, version, saved);
      this.memory.set(key, { at: Date.now(), saved: fresh });
      await this.writeDisk(key, fresh);
      return fresh.prompt;
    } catch (error) {
      if (!(error instanceof VeranoUnreachable)) throw error;
      if (!saved) throw error;
      const copy = { ...saved.prompt, fromCache: true };
      this.onFallback?.(
        `Verano could not be reached (${error.message}); using the saved copy of '${name}' (version ${copy.version}).`,
        copy,
      );
      return copy;
    }
  }

  private async fetchPrompt(
    name: string,
    label: string | null,
    version: number | undefined,
    saved: Saved | undefined,
  ): Promise<Saved> {
    const query = new URLSearchParams();
    if (label !== null) query.set("label", label);
    if (version !== undefined) query.set("version", String(version));
    const url =
      `${this.base}${API_PREFIX}/projects/${this.project}/prompt-by-name/${encodeURIComponent(name)}` +
      (query.size > 0 ? `?${query}` : "");
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: "application/json",
    };
    if (saved?.etag) headers["If-None-Match"] = saved.etag;
    let response: Response;
    try {
      response = await this.doFetch(url, { headers, signal: AbortSignal.timeout(this.timeoutMs) });
    } catch (error) {
      throw new VeranoUnreachable(error instanceof Error ? error.message : String(error));
    }
    if (response.status === 304 && saved) {
      return { etag: saved.etag, prompt: { ...saved.prompt, fromCache: false } };
    }
    if (response.status >= 500)
      throw new VeranoUnreachable(`the server answered ${response.status}`);
    if (!response.ok) throw new VeranoRefused(await refusal(response), response.status);
    try {
      const data = (await response.json()) as Wire;
      return { etag: response.headers.get("ETag"), prompt: fromWire(data, false) };
    } catch {
      throw new VeranoUnreachable("the answer was not a Verano prompt");
    }
  }

  private async readDisk(key: string): Promise<Saved | undefined> {
    if (this.cacheDir === null) return undefined;
    try {
      const fs = await import("node:fs/promises");
      const path = await import("node:path");
      const data = JSON.parse(
        await fs.readFile(path.join(this.cacheDir, `${key}.json`), "utf8"),
      ) as Saved;
      return { etag: data.etag, prompt: { ...data.prompt, fromCache: true } };
    } catch {
      return undefined;
    }
  }

  /** Best effort: a cache that cannot be written must never break the app. */
  private async writeDisk(key: string, saved: Saved): Promise<void> {
    if (this.cacheDir === null) return;
    try {
      const fs = await import("node:fs/promises");
      const path = await import("node:path");
      await fs.mkdir(this.cacheDir, { recursive: true });
      const target = path.join(this.cacheDir, `${key}.json`);
      const temp = `${target}.${Date.now()}.tmp`;
      await fs.writeFile(temp, JSON.stringify(saved), "utf8");
      await fs.rename(temp, target);
    } catch {
      return;
    }
  }
}

async function refusal(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    if (body.error?.message) return body.error.message;
  } catch {
    // fall through to the generic message
  }
  return `Verano refused the request (HTTP ${response.status}).`;
}
