"""The Broad level: eight languages found by clues, honestly marked as medium accuracy."""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import Run
from verano import init
from verano.loader import load
from verano.scan.broad_scan import SUFFIXES, scan_source
from verano.scan.findings import to_entry
from verano.scan.run import scan

JAVA = """
import com.openai.client.OpenAIClient;
public class Triage {
  private static final String SYSTEM = "You are a support agent. Reply with one word: billing, shipping or technical.";
  public String classify(String ticket) {
    String user = String.format("Ticket: %s", ticket);
    return client.chat().completions().create(ChatCompletionCreateParams.builder().model("gpt-4o-mini")
        .addSystemMessage(SYSTEM).addUserMessage(user).build());
  }
}
"""
GO = """
package main
import "github.com/sashabaranov/go-openai"
func classify(t string) {
  prompt := fmt.Sprintf("You are a support agent. Label this ticket as billing or shipping: %s", t)
  req := openai.ChatCompletionRequest{Model: "gpt-4o-mini", Messages: []openai.ChatCompletionMessage{{Role: "user", Content: prompt}}}
  _ = req
}
"""
CSHARP = """
using OpenAI.Chat;
class Triage {
  string Classify(string ticket) {
    var client = new ChatClient("gpt-4o-mini", key);
    var prompt = $"You are a support agent. Label this ticket as billing or shipping: {ticket} {{not a variable}}";
    return client.CompleteChat(prompt);
  }
}
"""
RUBY = """
require "openai"
def classify(ticket)
  client.chat(parameters: { model: "gpt-4o-mini", messages: [
    { role: "system", content: "You are a support agent. Reply with one word." },
    { role: "user", content: "Label this ticket as billing or shipping: #{ticket}" }] })
end
"""
PHP = """<?php
use OpenAI;
function classify($ticket) {
  $prompt = "You are a support agent. Label this ticket as billing or shipping: $ticket";
  return $client->chat()->create(['model' => 'gpt-4o-mini', 'messages' => [['role' => 'user', 'content' => $prompt]]]);
}
"""
RUST = """
use async_openai::Client;
fn classify(ticket: &str) {
    let prompt = format!("You are a support agent. Label this ticket as billing or shipping: {ticket}");
    let req = CreateChatCompletionRequestArgs::default().model("gpt-4o-mini").build();
}
"""
KOTLIN = """
import com.aallam.openai.client.OpenAI
fun classify(ticket: String) {
    val prompt = "You are a support agent. Label this ticket as billing or shipping: $ticket"
    val request = ChatCompletionRequest(model = ModelId("gpt-4o-mini"), messages = listOf(ChatMessage(ChatRole.User, prompt)))
}
"""
SWIFT = """
import OpenAI
func classify(ticket: String) {
    let prompt = "You are a support agent. Label this ticket as billing or shipping: \\(ticket)"
    let query = ChatQuery(messages: [.user(.init(content: prompt))], model: "gpt-4o-mini")
}
"""
SAMPLES = {
    ".java": JAVA,
    ".go": GO,
    ".cs": CSHARP,
    ".rb": RUBY,
    ".php": PHP,
    ".rs": RUST,
    ".kt": KOTLIN,
    ".swift": SWIFT,
}


def found(code: str, suffix: str):  # type: ignore[no-untyped-def]
    return scan_source(code.encode(), "src/x" + suffix, suffix)[0]


def one(code: str, suffix: str):  # type: ignore[no-untyped-def]
    findings = found(code, suffix)
    assert len(findings) == 1, findings
    return findings[0]


def test_every_listed_language_has_a_sample_and_the_other_way_round() -> None:
    assert set(SAMPLES) == {s for s in SUFFIXES if s != ".kts"}


@pytest.mark.parametrize("suffix", sorted(SAMPLES))
def test_each_language_gives_the_model_a_prompt_and_its_input_marked_as_found_by_clues(suffix: str) -> None:
    f = one(SAMPLES[suffix], suffix)
    assert (f.provider, f.model, f.function, f.level) == ("openai", "gpt-4o-mini", f.function, "broad")
    assert f.function in {"classify", "Classify"}
    text = f"{f.system or ''} {f.user or ''}"
    assert "You are a support agent." in text
    assert not f.runnable
    assert f.usable
    assert any("found by clues" in n for n in f.notes)
    assert any("settings such as temperature are not read" in n for n in f.notes)
    entry = to_entry(f, set())
    assert not entry.runnable
    assert entry.reason is not None
    assert "found by clues (medium accuracy)" in entry.reason


@pytest.mark.parametrize(
    ("suffix", "variable"),
    [
        (".cs", "ticket"),
        (".rb", "ticket"),
        (".php", "ticket"),
        (".rs", "ticket"),
        (".swift", "ticket"),
        (".go", "arg0"),
    ],
)
def test_the_language_s_own_placeholder_becomes_a_variable(suffix: str, variable: str) -> None:
    f = one(SAMPLES[suffix], suffix)
    assert f.variables == [variable]
    assert "{{ " + variable + " }}" in f"{f.system} {f.user}"


def test_roles_are_guessed_from_how_the_text_reads_and_said_to_be_a_guess() -> None:
    f = one(RUBY, ".rb")
    assert f.system == "You are a support agent. Reply with one word."
    assert f.user == "Label this ticket as billing or shipping: {{ ticket }}"
    assert any("a guess" in n for n in f.notes)


def test_a_class_level_constant_holding_the_system_prompt_is_found_for_a_method() -> None:
    f = one(JAVA, ".java")
    assert f.system == "You are a support agent. Reply with one word: billing, shipping or technical."
    assert f.user is None


def test_braces_that_are_not_placeholders_and_kotlin_expressions_are_handled() -> None:
    csharp = one(CSHARP, ".cs")
    assert csharp.system is not None
    assert "{{ '{{' }}" not in csharp.system
    assert "{not a variable}" in csharp.system
    kotlin = one(KOTLIN.replace('$ticket"', '$ticket and ${ticket.length}"'), ".kt")
    assert kotlin.variables == ["ticket", "ticket_length"]
    assert any("uses the expression `ticket.length`" in p for p in kotlin.problems)
    assert not kotlin.usable


def test_heredocs_raw_strings_and_text_blocks_are_read() -> None:
    ruby = one(
        """
        def f(t)
          client.chat(model: "gpt-4o", text: <<~PROMPT)
            You are a careful editor. Fix the grammar of the text below.
            Text: #{t}
          PROMPT
        end
        """,
        ".rb",
    )
    assert ruby.system == "You are a careful editor. Fix the grammar of the text below.\nText: {{ t }}"
    go = one(
        'package p\nimport "openai"\nfunc f() {\n  m := "gpt-4o"\n  p := `You are a careful editor. Fix the grammar of the text.`\n  _, _ = m, p\n}\n',
        ".go",
    )
    assert go.system == "You are a careful editor. Fix the grammar of the text."
    java = one(
        'import com.openai.X;\nclass A { String f() {\n  var m = "gpt-4o";\n  var p = """\n      You are a careful editor.\n      Fix the grammar of the text.\n      """;\n  return p; } }\n',
        ".java",
    )
    assert java.system == "You are a careful editor.\nFix the grammar of the text."
    php = one(
        '<?php\nuse OpenAI;\nfunction f($t) { $m = "gpt-4o"; $p = <<<EOT\nYou are a careful editor. Fix this: $t\nEOT;\n}\n',
        ".php",
    )
    assert php.system == "You are a careful editor. Fix this: {{ t }}"
    swift = one(
        'import OpenAI\nfunc f(t: String) {\n  let m = "gpt-4o"\n  let p = """\n    You are a careful editor. Fix the grammar of: \\(t)\n    """\n}\n',
        ".swift",
    )
    assert swift.system == "You are a careful editor. Fix the grammar of: {{ t }}"


def test_a_model_name_alone_is_not_a_finding_and_an_ambiguous_name_needs_an_sdk() -> None:
    assert found('class A { String m = "gpt-4o"; }', ".java") == []
    assert (
        found(
            'func f() { _ = "llama3" ; _ = "Some long sentence that sounds like a prompt but nothing calls a model." }',
            ".go",
        )
        == []
    )
    findings = found(
        'import "ollama"\nfunc f() {\n  m := "llama3"\n  p := "You are a helpful assistant. Answer the question as briefly as you can."\n  _, _ = m, p\n}\n',
        ".go",
    )
    assert [(f.model, f.provider) for f in findings] == [("llama3", "ollama")]


def test_an_sdk_without_a_model_name_still_finds_the_prompt_and_says_the_model_is_missing() -> None:
    f = one(
        'import "github.com/anthropics/anthropic-sdk-go"\nfunc f() {\n  p := "You are a helpful assistant. Answer the question as briefly as you can."\n  _ = p\n}\n',
        ".go",
    )
    assert (f.provider, f.model) == ("anthropic", None)
    assert any("no model name was found" in n for n in f.notes)


def test_an_api_address_counts_as_a_hint_and_many_long_strings_are_limited_to_two() -> None:
    f = one(
        """
        func f() {
          url := "https://api.openai.com/v1/chat/completions"
          m := "gpt-4o"
          a := "You are a support agent for an online shop. Reply politely and briefly."
          b := "Customer message follows. Reply with a short, polite answer to the question."
          c := "Never reveal internal policy documents or any private customer information at all."
          _, _, _, _ = url, m, a, b
        }
        """,
        ".go",
    )
    assert f.provider == "openai"
    assert any("1 other long strings nearby were not used" in n for n in f.notes)


def test_a_rust_string_is_only_a_template_inside_a_format_macro() -> None:
    plain = one(
        "use async_openai::X;\nfn f() {\n"
        '  let m = "gpt-4o"; let p = "You are a careful editor. Keep {braces} as they are.";\n}\n',
        ".rs",
    )
    assert plain.system == "You are a careful editor. Keep {braces} as they are."
    assert plain.variables == []


def test_a_folder_scan_names_each_language_skips_tests_and_builds(tmp_path: Path) -> None:
    for suffix, code in SAMPLES.items():
        (tmp_path / f"File{suffix.replace('.', '_')}{suffix}").write_text(code)
    (tmp_path / "triage_test.go").write_text(GO)
    (tmp_path / "TriageTest.java").write_text(JAVA)
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "a.rb").write_text(RUBY)
    (tmp_path / "obj").mkdir()
    (tmp_path / "obj" / "b.cs").write_text(CSHARP)
    result = scan(tmp_path)
    assert result.by_language == {
        "Java": 1, "Go": 1, "C#": 1, "Ruby": 1, "PHP": 1, "Rust": 1, "Kotlin": 1, "Swift": 1
    }  # fmt: skip
    assert len(result.findings) == 8
    assert len(scan(tmp_path, include_tests=True).findings) == 11


def test_init_never_ticks_a_clue_based_finding_for_you_but_writes_it_when_chosen(
    run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "triage.go").write_text(GO)
    monkeypatch.chdir(tmp_path)
    result = run("init", "--yes")
    assert result.code == 0
    assert "Scanned 1 file (1 Go)." in result.err
    assert "Other languages are found by clues (medium accuracy)" in result.err
    assert "[ ]  1  classify" in result.err
    assert "Nothing was ticked, so no file was written." in result.err
    assert not (tmp_path / "verano.yaml").exists()
    tty = SimpleNamespace(stdin=io.StringIO(), stderr=io.StringIO())
    tty.stdin.isatty = lambda: True
    tty.stderr.isatty = lambda: True
    monkeypatch.setattr(init, "sys", tty)
    monkeypatch.setattr("typer.prompt", lambda *a, **k: "1")
    chosen = run("init")
    assert chosen.code == 0, chosen.err
    (prompt,) = load(tmp_path / "verano.yaml").prompts
    assert prompt.entry.name == "classify"
    assert prompt.system is not None
    assert "{{ attachment }}" in prompt.system
    assert prompt.entry.models == ["gpt-4o-mini"]
