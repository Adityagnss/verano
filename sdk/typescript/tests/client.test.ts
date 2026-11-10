/**
 * The TypeScript SDK against a fake `fetch`: a fetch, the ETag, the fallback when Verano cannot be reached, a refusal
 * that the saved copy must never hide, and rendering (scenario S8.2). Run with `npm test` (vitest, globals on).
 */
import { mkdtemp, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  Verano,
  VeranoError,
  VeranoRefused,
  VeranoUnreachable,
  render,
} from "../src/index";

const PROJECT = "11111111-2222-3333-4444-555555555555";
const PROMPT = {
  name: "triage",
  label: "production",
  version: 3,
  version_id: "v3",
  system_template: "You triage tickets for {{ team }}.",
  user_template: "Ticket: {{ ticket }}",
  variables: ["team", "ticket"],
  default_params: { temperature: 0 },
  updated_at: "2026-11-10T09:00:00Z",
};

interface Seen {
  url: string;
  headers: Record<string, string>;
}

/** A Verano that answers `prompt-by-name`; what it does next is set by the test. */
function fakeVerano() {
  const state = {
    status: 200,
    etag: '"v3"',
    prompt: { ...PROMPT },
    down: false,
    seen: [] as Seen[],
  };
  const fetcher = (async (
    url: string,
    init?: { headers?: Record<string, string> },
  ) => {
    state.seen.push({ url, headers: init?.headers ?? {} });
    if (state.down) throw new TypeError("fetch failed: connection refused");
    if (state.status !== 200) {
      return new Response(
        JSON.stringify({ error: { message: `fake answer ${state.status}` } }),
        {
          status: state.status,
        },
      );
    }
    if (init?.headers?.["If-None-Match"] === state.etag)
      return new Response(null, { status: 304 });
    return new Response(JSON.stringify(state.prompt), {
      status: 200,
      headers: { ETag: state.etag },
    });
  }) as unknown as typeof fetch;
  return { state, fetcher };
}

async function make(
  fake: ReturnType<typeof fakeVerano>,
  extra: Record<string, unknown> = {},
) {
  const cacheDir = await mkdtemp(join(tmpdir(), "verano-sdk-"));
  const warnings: string[] = [];
  const verano = new Verano({
    baseUrl: "http://verano.test",
    token: "vrn_test",
    projectId: PROJECT,
    cacheDir,
    fetch: fake.fetcher,
    onFallback: (message: string) => warnings.push(message),
    ...extra,
  });
  return { verano, cacheDir, warnings };
}

describe("fetching", () => {
  it("asks for the label with the token and saves the answer", async () => {
    const fake = fakeVerano();
    const { verano, cacheDir } = await make(fake);
    const prompt = await verano.prompt("triage", { label: "staging" });
    expect(prompt).toMatchObject({
      name: "triage",
      version: 3,
      fromCache: false,
    });
    expect(fake.state.seen[0].url).toBe(
      `http://verano.test/api/v1/projects/${PROJECT}/prompt-by-name/triage?label=staging`,
    );
    expect(fake.state.seen[0].headers.Authorization).toBe("Bearer vrn_test");
    expect(
      (await readdir(cacheDir)).some((file) => file.endsWith(".json")),
    ).toBe(true);
  });

  it("sends the saved ETag, so an unchanged prompt costs an empty answer", async () => {
    const fake = fakeVerano();
    const { verano } = await make(fake);
    await verano.prompt("triage");
    const again = await verano.prompt("triage");
    expect(fake.state.seen[1].headers["If-None-Match"]).toBe('"v3"');
    expect(again).toMatchObject({ version: 3, fromCache: false });
  });

  it("replaces the saved copy when the prompt changed", async () => {
    const fake = fakeVerano();
    const { verano, warnings } = await make(fake);
    await verano.prompt("triage");
    fake.state.prompt = {
      ...PROMPT,
      version: 4,
      version_id: "v4",
      system_template: "New text.",
    };
    fake.state.etag = '"v4"';
    expect((await verano.prompt("triage")).version).toBe(4);
    fake.state.down = true; // the newest copy is the one served in an outage
    const saved = await verano.prompt("triage");
    expect(saved).toMatchObject({
      systemTemplate: "New text.",
      fromCache: true,
    });
    expect(warnings).toHaveLength(1);
  });

  it("uses a pinned version instead of the label, and max age skips the request", async () => {
    const fake = fakeVerano();
    const { verano } = await make(fake, { maxAgeMs: 60_000 });
    await verano.prompt("triage", { version: 2 });
    expect(fake.state.seen[0].url.endsWith("?version=2")).toBe(true);
    await verano.prompt("triage", { version: 2 });
    expect(fake.state.seen).toHaveLength(1);
  });
});

describe("when Verano cannot be reached", () => {
  it("serves the saved copy and says so", async () => {
    const fake = fakeVerano();
    const { verano, warnings } = await make(fake);
    await verano.prompt("triage");
    fake.state.down = true;
    const prompt = await verano.prompt("triage");
    expect(prompt).toMatchObject({ version: 3, fromCache: true });
    expect(warnings[0]).toContain("could not be reached");
  });

  it("serves the saved copy on a server error as well", async () => {
    const fake = fakeVerano();
    const { verano, warnings } = await make(fake);
    await verano.prompt("triage");
    fake.state.status = 503;
    expect((await verano.prompt("triage")).fromCache).toBe(true);
    expect(warnings).toHaveLength(1);
  });

  it("is an error that says so when nothing was saved", async () => {
    const fake = fakeVerano();
    fake.state.down = true;
    const { verano } = await make(fake);
    await expect(verano.prompt("triage")).rejects.toBeInstanceOf(
      VeranoUnreachable,
    );
  });

  it("uses the copy on disk after a restart", async () => {
    const fake = fakeVerano();
    const { verano, cacheDir } = await make(fake);
    await verano.prompt("triage");
    fake.state.down = true;
    const restarted = new Verano({
      baseUrl: "http://verano.test",
      token: "vrn_test",
      projectId: PROJECT,
      cacheDir,
      fetch: fake.fetcher,
    });
    expect((await restarted.prompt("triage")).fromCache).toBe(true);
  });
});

describe("a no from Verano", () => {
  it.each([401, 403, 404])(
    "is thrown and never hidden behind the saved copy (%i)",
    async (status) => {
      const fake = fakeVerano();
      const { verano, warnings } = await make(fake);
      await verano.prompt("triage");
      fake.state.status = status;
      const failure = await verano
        .prompt("triage")
        .catch((error: unknown) => error);
      expect(failure).toBeInstanceOf(VeranoRefused);
      expect((failure as VeranoRefused).status).toBe(status);
      expect((failure as VeranoRefused).message).toBe(`fake answer ${status}`);
      expect(warnings).toHaveLength(0);
    },
  );
});

describe("setup and cache", () => {
  it("needs the address, the token and the project", () => {
    const previous = { ...process.env };
    delete process.env.VERANO_URL;
    delete process.env.VERANO_API_TOKEN;
    delete process.env.VERANO_PROJECT_ID;
    try {
      expect(() => new Verano({ baseUrl: "http://x" })).toThrow(
        /read-only token/,
      );
    } finally {
      Object.assign(process.env, previous);
    }
  });

  it("never lets a corrupt or unwritable cache break the app", async () => {
    const fake = fakeVerano();
    const { verano, cacheDir } = await make(fake);
    await verano.prompt("triage");
    for (const file of await readdir(cacheDir))
      await writeFile(join(cacheDir, file), "{ not json");
    const fresh = new Verano({
      baseUrl: "http://verano.test",
      token: "t",
      projectId: PROJECT,
      cacheDir: join(cacheDir, "nope", "\0bad"),
      fetch: fake.fetcher,
    });
    expect((await fresh.prompt("triage")).version).toBe(3);
  });
});

describe("render", () => {
  it("fills every placeholder and names what is missing", async () => {
    const fake = fakeVerano();
    const { verano } = await make(fake);
    const prompt = await verano.prompt("triage");
    expect(
      render(prompt, { team: "billing", ticket: "I was charged twice" }),
    ).toEqual({
      system: "You triage tickets for billing.",
      user: "Ticket: I was charged twice",
    });
    expect(() => render(prompt, { team: "billing" })).toThrow(VeranoError);
    expect(() => render(prompt, { team: "billing" })).toThrow(/ticket/);
  });
});
