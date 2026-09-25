"""
Sandboxed Jinja2 rendering.

Two kinds of templates are rendered here: user prompt templates (untrusted, from the
database) and the system's own LLM prompts (`<module>/prompts/*.jinja`, versioned in git).
Both use a sandboxed environment with strict undefined variables, so a template can only
insert values and can never reach Python internals or silently render a missing variable.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment


def sandboxed_environment(loader: FileSystemLoader | None = None) -> ImmutableSandboxedEnvironment:
    return ImmutableSandboxedEnvironment(
        loader=loader,
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


@lru_cache(maxsize=32)
def _module_environment(prompts_dir: Path) -> ImmutableSandboxedEnvironment:
    return sandboxed_environment(FileSystemLoader(prompts_dir))


def render_system_prompt(prompts_dir: Path, name: str, **values: Any) -> str:
    return _module_environment(prompts_dir).get_template(name).render(**values)


def render_string(template: str, **values: Any) -> str:
    return sandboxed_environment().from_string(template).render(**values)
