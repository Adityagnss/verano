"""The Python scanner: what it reads, what it refuses to guess, and how prompts become Verano templates."""

from pathlib import Path
from textwrap import dedent

import pytest

from verano.scan.findings import ScanResult, to_entry
from verano.scan.python_scan import escape, format_template, infer_provider, scan_source
from verano.scan.run import scan


def found(code: str):  # type: ignore[no-untyped-def]
    findings, other = scan_source(dedent(code), "app/x.py")
    return findings, other


def one(code: str):  # type: ignore[no-untyped-def]
    findings, _ = found(code)
    assert len(findings) == 1, findings
    return findings[0]


def test_an_openai_call_gives_model_settings_and_the_prompt_with_its_variable() -> None:
    f = one(
        """
        def classify(ticket):
            return client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                max_tokens=50,
                seed=7,
                stop=["END", "STOP"],
                messages=[
                    {"role": "system", "content": "Classify the ticket. Reply with one word."},
                    {"role": "user", "content": f"Ticket: {ticket}"},
                ],
            )
        """
    )
    assert (f.provider, f.model, f.function, f.line) == ("openai", "gpt-4o-mini", "classify", 3)
    assert f.params == {"temperature": 0.2, "max_tokens": 50, "seed": 7, "stop": ["END", "STOP"]}
    assert f.system == "Classify the ticket. Reply with one word."
    assert f.user == "Ticket: {{ ticket }}"
    assert f.variables == ["ticket"]
    assert f.problems == []
    assert f.runnable


def test_names_assigned_in_the_function_or_at_the_top_of_the_file_are_followed() -> None:
    f = one(
        """
        MODEL = "gpt-4o"
        SYSTEM = "You are a " + "careful reviewer."
        LIMIT = 300

        def review(text):
            prompt = f"Review this:\\n{text}"
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
            return client.chat.completions.create(model=MODEL, messages=messages, max_tokens=LIMIT)
        """
    )
    assert f.model == "gpt-4o"
    assert f.system == "You are a careful reviewer."
    assert f.user == "Review this:\n{{ text }}"
    assert f.params == {"max_tokens": 300}


def test_a_message_that_is_only_a_variable_is_an_input() -> None:
    f = one(
        """
        SYSTEM = "Summarize."
        def run(user_text):
            return client.chat.completions.create(model="gpt-4o", messages=[
                {"role": "system", "content": SYSTEM}, {"role": "user", "content": user_text}])
        """
    )
    assert f.user == "{{ user_text }}"
    entry = to_entry(f, set())
    assert entry.user is None
    assert entry.system == "Summarize."
    assert entry.runnable


def test_anthropic_litellm_responses_and_gemini_calls_are_read() -> None:
    anthropic = one(
        """
        def f(q):
            return client.messages.create(model="claude-3-5-haiku-latest", max_tokens=200, temperature=0,
                system="Answer briefly.", messages=[{"role": "user", "content": f"Q: {q}"}])
        """
    )
    assert (anthropic.provider, anthropic.system, anthropic.user) == ("anthropic", "Answer briefly.", "Q: {{ q }}")
    blocks = one(
        """
        def f(q):
            return client.messages.create(model="claude-sonnet-4-5", max_tokens=9,
                system=[{"type": "text", "text": "Be kind."}, {"type": "text", "text": "Be short."}],
                messages=[{"role": "user", "content": q}])
        """
    )
    assert blocks.system == "Be kind.\n\nBe short."
    lite = one(
        """
        import litellm
        def f(t):
            return litellm.completion(model="anthropic/claude-3-5-haiku", messages=[{"role": "user", "content": t}])
        """
    )
    assert (lite.provider, lite.model) == ("anthropic", "claude-3-5-haiku")
    responses = one(
        """
        def f(t):
            return client.responses.create(model="gpt-4.1", instructions="Be formal.", input=f"Rewrite: {t}")
        """
    )
    assert (responses.system, responses.user, responses.provider) == ("Be formal.", "Rewrite: {{ t }}", "openai")
    gemini = one(
        """
        import google.generativeai as genai
        model = genai.GenerativeModel("gemini-1.5-flash")
        def f(t):
            return model.generate_content(f"Translate: {t}")
        """
    )
    assert (gemini.provider, gemini.model, gemini.user) == ("gemini", "gemini-1.5-flash", "Translate: {{ t }}")


def test_format_templates_and_wrappers_are_read() -> None:
    f = one(
        '''
        from textwrap import dedent
        TEMPLATE = dedent("""
            Classify {ticket} as {label_set}.
        """).strip()
        def f(t):
            return client.chat.completions.create(model="gpt-4o", messages=[
                {"role": "user", "content": TEMPLATE.format(ticket=t, label_set="a or b")}])
        '''
    )
    assert f.user == "Classify {{ ticket }} as {{ label_set }}."
    assert f.variables == ["ticket", "label_set"]
    assert not f.runnable


def test_text_that_looks_like_a_template_tag_is_written_as_a_literal() -> None:
    assert escape("use {{ and {% tags %}") == "use {{ '{{' }} and {{ '{%' }} tags %}"
    assert escape("a { single } brace") == "a { single } brace"
    template = format_template('Return {{"a": 1}} for {name}')
    assert template.text == 'Return {"a": 1} for {{ name }}'
    assert template.variables == ["name"]


@pytest.mark.parametrize(
    ("snippet", "needle"),
    [
        ("messages=history", "the messages come from `history`"),
        ('messages=[{"role": "user", "content": build_prompt(x)}]', "calling `build_prompt(…)`"),
        ('messages=[{"role": "user", "content": f"{item.title} and {x}"}]', "uses the expression `{item.title}`"),
        ('messages=[{"role": "user", "content": "a %s" % x}]', "uses %-style formatting"),
        ('messages=[*base, {"role": "user", "content": "x"}]', "a message is not written"),
        ("**options", "passes **options"),
    ],
)
def test_what_cannot_be_read_is_named_and_never_guessed(snippet: str, needle: str) -> None:
    f = one(
        f'def f(x, history, base, options):\n    return client.chat.completions.create(model="gpt-4o", {snippet})\n'
    )
    assert any(needle in p for p in f.problems), f.problems
    assert not f.usable


def test_a_model_that_is_not_fixed_is_a_note_not_a_failure() -> None:
    f = one(
        """
        def f(cfg):
            return client.chat.completions.create(model=cfg.model, temperature=cfg.t,
                messages=[{"role": "user", "content": "hi"}])
        """
    )
    assert f.model is None
    assert "the model is not a fixed value" in f.notes
    assert any(n.startswith("temperature is not a fixed value") for n in f.notes)
    assert f.usable


def test_earlier_example_messages_are_mentioned_but_not_included() -> None:
    f = one(
        """
        def f(t):
            return client.chat.completions.create(model="gpt-4o", messages=[
                {"role": "system", "content": "Tag it."},
                {"role": "user", "content": "great"}, {"role": "assistant", "content": "positive"},
                {"role": "user", "content": t}])
        """
    )
    assert f.user == "{{ t }}"
    assert any("2 earlier example messages (few-shot)" in n for n in f.notes)


def test_langchain_templates_get_their_model_when_there_is_exactly_one() -> None:
    f = one(
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        prompt = ChatPromptTemplate.from_messages([("system", "Summarize."), ("human", "{text}")])
        """
    )
    assert (f.kind, f.provider, f.model, f.params) == ("prompt", "openai", "gpt-4o-mini", {"temperature": 0})
    assert (f.system, f.user, f.variables) == ("Summarize.", "{{ text }}", ["text"])
    two = one(
        """
        a = ChatOpenAI(model="gpt-4o")
        b = ChatAnthropic(model="claude-3-5-haiku")
        prompt = ChatPromptTemplate.from_template("Say {x}")
        """
    )
    assert two.model is None
    assert any("no single model" in n for n in two.notes)


def test_tools_structured_output_and_retrieval_are_noted_for_later() -> None:
    findings, other = found(
        """
        def f(q):
            vectors = client.embeddings.create(model="text-embedding-3-small", input=q)
            docs = store.similarity_search(q, k=4)
            splitter = RecursiveCharacterTextSplitter(chunk_size=500)
            return client.chat.completions.create(model="gpt-4o", tools=[t], response_format={"type": "json_object"},
                messages=[{"role": "user", "content": q}])
        """
    )
    (f,) = findings
    assert any("tool use" in n for n in f.notes)
    assert any("structured response" in n for n in f.notes)
    assert {o.split(": ", 1)[1] for o in other} == {
        "an embedding model", "document retrieval", "a text splitter (chunking)", "tools (tool use)"
    }  # fmt: skip


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-4o", ("openai", "gpt-4o")),
        ("o3-mini", ("openai", "o3-mini")),
        ("claude-3-opus", ("anthropic", "claude-3-opus")),
        ("groq/llama-3.3-70b", ("groq", "llama-3.3-70b")),
        ("together_ai/meta/llama", ("together", "meta/llama")),
        ("meta-llama/Llama-3", (None, "meta-llama/Llama-3")),
        ("llama3", (None, "llama3")),
        (None, (None, None)),
    ],
)
def test_the_provider_is_taken_from_the_name_only_where_the_name_says_so(
    model: str | None, expected: tuple[str | None, str | None]
) -> None:
    assert infer_provider(model) == expected


def test_one_input_becomes_attachment_several_are_offered_unticked_with_the_reason() -> None:
    renamed = to_entry(
        one(
            """
            def classify_ticket(ticket):
                return client.chat.completions.create(model="gpt-4o", messages=[
                    {"role": "system", "content": f"Tag {ticket}."}, {"role": "user", "content": f"T: {ticket}"}])
            """
        ),
        set(),
    )
    assert renamed.name == "classify-ticket"
    assert (renamed.system, renamed.user) == ("Tag {{ attachment }}.", "T: {{ attachment }}")
    assert renamed.runnable
    assert any("`ticket` is now `attachment`" in c for c in renamed.comments)
    many = to_entry(
        one(
            """
            def f(a, b):
                return client.chat.completions.create(model="gpt-4o", messages=[
                    {"role": "user", "content": f"{a} {b}"}])
            """
        ),
        {"f"},
    )
    assert not many.runnable
    assert many.name == "f-2"
    assert many.reason is not None
    assert "2 inputs (a, b)" in many.reason


def test_a_folder_scan_skips_dependencies_tests_and_unreadable_files(tmp_path: Path) -> None:
    call = 'client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])\n'
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("x = " + call)
    for hidden in ("node_modules", ".venv", "tests", "build"):
        (tmp_path / hidden).mkdir()
        (tmp_path / hidden / "b.py").write_text("x = " + call)
    (tmp_path / "app" / "broken.py").write_text("def (:\n")
    (tmp_path / "app" / "latin.py").write_bytes(b"x = '\xe9'\n")
    (tmp_path / "app" / "big.py").write_text("#" * 1_000_001)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cases.csv").write_text("a\n1\n")
    (tmp_path / "other.csv").write_text("a\n1\n")
    result: ScanResult = scan(tmp_path)
    assert [f.file for f in result.findings] == ["app/a.py"]
    assert result.files_scanned == 1
    assert sorted(s.split(":")[0] for s in result.files_skipped) == ["app/big.py", "app/broken.py", "app/latin.py"]
    assert result.data_files == ["data/cases.csv"]
    assert len(scan(tmp_path, include_tests=True).findings) == 2
