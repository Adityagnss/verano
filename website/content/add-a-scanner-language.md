# Add a language to `verano init`

`verano init` reads Python, TypeScript and JavaScript with real syntax-tree logic, and eight more
languages at the **Broad** level: it finds model names, SDK names, API addresses and long
instruction-like text near them. Adding another language to the Broad level is one table entry
plus a test. (Reading a language *properly*, with its SDK call shapes, is a bigger piece of work
and would be a new scanner next to `python_scan.py` and `ts_scan.py`.)

Everything below is in `cli/`.

## 1. Install the grammar

Find the language's tree-sitter package on PyPI (for example `tree-sitter-scala`), then:

```bash
cd cli
uv add tree-sitter-scala
```

Set its floor in `pyproject.toml` to the version you tested (`tree-sitter-scala>=0.23.1`): grammar
packages are small leaf dependencies that have to match each other, so they are pinned to what
was tested.

## 2. Find the node names

Each grammar names its string and function nodes differently. Parse a small sample and print the
kinds that matter:

```python
import importlib
from tree_sitter import Language, Parser

module = importlib.import_module("tree_sitter_scala")
tree = Parser(Language(module.language())).parse(b'def f(t: String) = s"Label $t now" + "gpt-4o"')

def walk(node):
    if "string" in node.type or "function" in node.type or "method" in node.type:
        print(node.type, node.text[:40])
    for child in node.children:
        walk(child)

walk(tree.root_node)
```

Note the outermost string node types (`strings`), the function and method node types (`functions`),
and which function name PyPI's package uses (`language` for most; PHP uses `language_php`).

## 3. Add the entry

In `src/verano/scan/broad_scan.py`, add to `LANGS`:

```python
".scala": _lang(
    "Scala", "tree_sitter_scala", {"string", "interpolated_string_expression"},
    {"function_definition"}, "scala",
),
```

The last argument is the **interpolation style**: how the language writes a placeholder inside a
string. Existing styles are `ruby` (`#{x}`), `kotlin` (`$x`, `${x}`), `swift` (`\(x)`), `php`,
`csharp` (`$"{x}"`), `rust` (`{x}` inside `format!`) and `printf` (`%s`, for Java and Go). If your
language's style is new, add a small function next to `_kotlin` or `_csharp` that turns the string
body into a `Text` (literal parts escaped, each placeholder a `variable(...)`), and one line in
`interpolate`. If the language only needs plain text, give it a style with no function: its strings
are used as they are.

Also add the SDK words to `SDK_HINTS` if the language's package names are not already covered
(`openai`, `anthropic`, `generativeai`, `groq`, `mistral`, `ollama`), and the test-file pattern to
`TEST_FILE` in `scan/walk.py` (for example `Spec\.scala`).

## 4. Test it

In `tests/test_scan_broad.py` add a realistic sample to the module constants and to `SAMPLES`, and
run:

```bash
uv run pytest -q tests/test_scan_broad.py
```

The shared tests then check that the sample gives the model, a prompt containing the instruction
sentence, the "found by clues" notes, that it is not ticked for the user, and that a folder scan
counts the language. Add one more test for anything particular to the language (a heredoc, a raw
string, an unusual interpolation).

## 5. Say so

Add the language to the list in `cli/README.md` ("How `init` reads your code") and in the message at
the end of `init.py`.

## Why a Broad entry is never ticked for you

The role of each text (system or user) and which strings belong to the call are guesses made from
clues. `init --yes` writes only findings it read from a syntax tree; a clue-based finding is listed
unticked, with the reason, and is written only when the user chooses its number.
