"""The TypeScript / JavaScript scanner: real syntax trees, template literals, SDK shapes and honest gaps."""

from pathlib import Path
from textwrap import dedent

import pytest

from tests.conftest import Run
from verano.loader import load
from verano.scan.findings import to_entry
from verano.scan.run import scan
from verano.scan.ts_scan import scan_source, unescape


def found(code: str, suffix: str = ".ts"):  # type: ignore[no-untyped-def]
    return scan_source(dedent(code).encode(), "src/x" + suffix, suffix)


def one(code: str, suffix: str = ".ts"):  # type: ignore[no-untyped-def]
    findings, _ = found(code, suffix)
    assert len(findings) == 1, findings
    return findings[0]


def test_an_openai_call_in_typescript_gives_model_settings_and_the_prompt() -> None:
    f = one(
        """
        export async function classifyTicket(ticket: string) {
          const res = await client.chat.completions.create({
            model: "gpt-4o-mini",
            temperature: 0.2,
            max_tokens: 50,
            seed: 7,
            stop: ["END", "STOP"],
            messages: [
              { role: "system", content: "Classify the ticket. Reply with one word." },
              { role: "user", content: `Ticket: ${ticket}` },
            ],
          });
          return res;
        }
        """
    )
    assert (f.provider, f.model, f.function, f.line) == ("openai", "gpt-4o-mini", "classifyTicket", 3)
    assert f.params == {"temperature": 0.2, "max_tokens": 50, "seed": 7, "stop": ["END", "STOP"]}
    assert (f.system, f.user, f.variables) == (
        "Classify the ticket. Reply with one word.",
        "Ticket: {{ ticket }}",
        ["ticket"],
    )
    assert f.runnable


def test_constants_in_the_function_or_at_the_top_of_the_file_are_followed() -> None:
    f = one(
        """
        const MODEL = "gpt-4o";
        const SYSTEM = "You are a " + "careful reviewer.";
        const LIMIT = 300;
        const arrow = async (text) => {
          const prompt = `Review this:\\n${text}`;
          return client.chat.completions.create({
            model: MODEL, max_tokens: LIMIT,
            messages: [{ role: "system", content: SYSTEM }, { role: "user", content: prompt }],
          });
        };
        """
    )
    assert (f.model, f.function, f.params) == ("gpt-4o", "arrow", {"max_tokens": 300})
    assert (f.system, f.user) == ("You are a careful reviewer.", "Review this:\n{{ text }}")


def test_prompts_written_as_joined_arrays_trimmed_text_and_with_escapes_are_read() -> None:
    f = one(
        r"""
        const SYSTEM = [
          "You are a classifier.",
          "Answer with 'billing' or \"shipping\".",
          "Use a tab:\there.",
        ].join("\n");
        function go(q) {
          return client.chat.completions.create({ model: "gpt-4o", messages: [
            { role: "system", content: SYSTEM.trim() }, { role: "user", content: q }] });
        }
        """,
        ".js",
    )
    assert f.system == "You are a classifier.\nAnswer with 'billing' or \"shipping\".\nUse a tab:\there."
    assert f.user == "{{ q }}"
    assert to_entry(f, set()).user is None


def test_shorthand_content_and_destructured_parameters_are_inputs() -> None:
    f = one(
        """
        async function f({ ticket }: { ticket: string }) {
          const content = `T: ${ticket}`;
          return client.chat.completions.create({ model: "gpt-4o", messages: [{ role: "user", content }] });
        }
        """
    )
    assert (f.user, f.variables) == ("T: {{ ticket }}", ["ticket"])


def test_anthropic_vercel_responses_and_gemini_calls_are_read() -> None:
    anthropic = one(
        """
        const r = await client.messages.create({ model: "claude-3-5-haiku-latest", max_tokens: 200, temperature: 0,
          system: "Answer briefly.", messages: [{ role: "user", content: `Q: ${q}` }] });
        """
    )
    assert (anthropic.provider, anthropic.system, anthropic.user) == ("anthropic", "Answer briefly.", "Q: {{ q }}")
    vercel = one(
        """
        import { openai } from "@ai-sdk/openai";
        const { text } = await generateText({
          model: openai("gpt-4o-mini"), system: "Be formal.", prompt: `Rewrite: ${input}`,
          temperature: 0.3, maxTokens: 400, topP: 0.9, stopSequences: ["###"],
        });
        """
    )
    assert (vercel.provider, vercel.model, vercel.system, vercel.user) == (
        "openai",
        "gpt-4o-mini",
        "Be formal.",
        "Rewrite: {{ input }}",
    )
    assert vercel.params == {"temperature": 0.3, "max_tokens": 400, "top_p": 0.9, "stop": ["###"]}
    gateway = one(
        'const r = await streamText({ model: "anthropic/claude-3-5-haiku", messages: [{ role: "user", content: t }] });'
    )
    assert (gateway.provider, gateway.model) == ("anthropic", "claude-3-5-haiku")
    responses = one(
        "const r = await client.responses.create({"
        ' model: "gpt-4.1", instructions: "Be formal.", input: `Rewrite: ${t}` });'
    )
    assert (responses.system, responses.user) == ("Be formal.", "Rewrite: {{ t }}")
    gemini = one(
        """
        const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
        const result = await model.generateContent(`Translate: ${text}`);
        """
    )
    assert (gemini.provider, gemini.model, gemini.user) == ("gemini", "gemini-1.5-flash", "Translate: {{ text }}")


def test_langchain_templates_get_their_model_when_there_is_exactly_one() -> None:
    f = one(
        """
        import { ChatOpenAI } from "@langchain/openai";
        const llm = new ChatOpenAI({ model: "gpt-4o-mini", temperature: 0 });
        const prompt = ChatPromptTemplate.fromMessages([["system", "Summarize."], ["human", "{text}"]]);
        """
    )
    assert (f.kind, f.provider, f.model, f.params) == ("prompt", "openai", "gpt-4o-mini", {"temperature": 0})
    assert (f.system, f.user, f.variables) == ("Summarize.", "{{ text }}", ["text"])
    none = one('const p = PromptTemplate.fromTemplate("Say {x} and {y}");')
    assert none.model is None
    assert none.variables == ["x", "y"]
    assert any("no single model" in n for n in none.notes)


@pytest.mark.parametrize(
    ("snippet", "needle"),
    [
        ("messages: history", "the messages come from `history`"),
        ('messages: [{ role: "user", content: buildPrompt(x) }]', "calling `buildPrompt(…)`"),
        ('messages: [{ role: "user", content: `${item.title} and ${x}` }]', "uses the expression `${item.title}`"),
        ('messages: [{ role: "user", content: item.text }]', "uses the expression `item.text`"),
        ('messages: [...base, { role: "user", content: "x" }]', "a message is not written"),
        ('messages: [{ role: "user", content: "x" }], ...options', "spreads other options in"),
        ("messages: [{ role, content: 'x' }]", "no readable role"),
    ],
)
def test_what_cannot_be_read_is_named_and_never_guessed(snippet: str, needle: str) -> None:
    f = one(
        "function f(x, history, base, options, role, item) { return client.chat.completions.create("
        f'{{ model: "gpt-4o", {snippet} }}); }}'
    )
    assert any(needle in p for p in f.problems), f.problems
    assert not f.usable


def test_a_model_that_is_not_fixed_is_a_note_and_tools_and_retrieval_are_listed_for_later() -> None:
    findings, other = found(
        """
        async function f(cfg, q) {
          const vectors = await client.embeddings.create({ model: "text-embedding-3-small", input: q });
          const docs = await store.similaritySearch(q, 4);
          const splitter = new RecursiveCharacterTextSplitter({ chunkSize: 500 });
          return client.chat.completions.create({ model: cfg.model, temperature: cfg.t, tools: [t],
            messages: [{ role: "user", content: "hi" }] });
        }
        """
    )
    (f,) = findings
    assert f.model is None
    assert "the model is not a fixed value" in f.notes
    assert any(n.startswith("temperature is not a fixed value") for n in f.notes)
    assert any("tool use" in n for n in f.notes)
    assert f.usable
    assert {o.split(": ", 1)[1] for o in other} == {
        "an embedding model", "document retrieval", "a text splitter (chunking)", "tools (tool use)"
    }  # fmt: skip


def test_escape_sequences_and_template_syntax_are_handled() -> None:
    assert unescape(r"a\nb\té\x41\u{1F600}\'\\") == "a\nb\té" + "A" + "😀" + "'\\"
    f = one(
        "const r = await client.chat.completions.create({ model: 'gpt-4o', "
        'messages: [{ role: "user", content: "Return {{ json }} {%" }] });'
    )
    assert f.user == "Return {{ '{{' }} json }} {{ '{%' }}"


def test_a_file_with_broken_syntax_still_gives_what_can_be_read_with_a_warning_note() -> None:
    findings, _ = found(
        """
        const r = await client.chat.completions.create({
          model: "gpt-4o", messages: [{ role: "user", content: "hi" }],
        });
        const broken = ((( ;
        """
    )
    (f,) = findings
    assert any("could not fully read" in n for n in f.notes)


def test_a_folder_scan_reads_every_language_and_skips_dependencies(tmp_path: Path) -> None:
    call = 'await client.chat.completions.create({ model: "gpt-4o", messages: [{ role: "user", content: "hi" }] });\n'
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("export const a = " + call)
    (tmp_path / "src" / "b.js").write_text("exports.b = " + call)
    (tmp_path / "src" / "c.tsx").write_text("export const C = async () => " + call)
    (tmp_path / "src" / "d.py").write_text(
        'client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "x"}])\n'
    )
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "e.js").write_text("exports.e = " + call)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "f.js").write_text("exports.f = " + call)
    result = scan(tmp_path)
    assert [f.file for f in result.findings] == ["src/a.ts", "src/b.js", "src/c.tsx", "src/d.py"]
    assert result.by_language == {"TypeScript/JavaScript": 3, "Python": 1}


def test_init_writes_a_loadable_file_for_a_typescript_project(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "triage.ts").write_text(
        dedent(
            """
            const SYSTEM = "Route the ticket to billing, shipping or technical.";
            export async function triage(ticket: string) {
              return client.chat.completions.create({
                model: "gpt-4o-mini", temperature: 0,
                messages: [{ role: "system", content: SYSTEM }, { role: "user", content: `Ticket: ${ticket}` }],
              });
            }
            """
        )
    )
    monkeypatch.chdir(tmp_path)
    result = run("init", "--yes")
    assert result.code == 0, result.err
    assert "Scanned 1 file (1 TypeScript/JavaScript)." in result.err
    (prompt,) = load(tmp_path / "verano.yaml").prompts
    assert prompt.entry.name == "triage"
    assert prompt.system == "Route the ticket to billing, shipping or technical."
    assert prompt.user == "Ticket: {{ attachment }}"
    assert prompt.entry.source is not None
    assert (prompt.entry.source.file, prompt.entry.source.line) == ("src/triage.ts", 4)
