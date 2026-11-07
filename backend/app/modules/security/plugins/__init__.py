"""
Attack case generators, registered as plugins (ADR 0035).

One file per attack family in this folder; a file adds its generator with `ATTACKS.add(id, AttackGenerator(...))` and
is picked up by `load_plugins`, so adding a family never edits a branch. A generator is plain data: a few *styles*
(how the attack is dressed up; `{goal}` marks where the objective goes) and a few *goals* (what the attacker wants,
with the safe behaviour that answers it). Combining them gives many different cases without calling any model, so the
pack works at zero cost; when a model is chosen it writes extra, app-specific attacks on top (`ask`).
"""

from dataclasses import dataclass

from app.core.registry import Registry


@dataclass(frozen=True)
class Goal:
    text: str
    safe: str  # what a safe answer does for this goal, in plain words (becomes the case's expected safe behaviour)


@dataclass(frozen=True)
class Seed:
    text: str
    safe_behaviour: str


@dataclass(frozen=True)
class AttackGenerator:
    id: str
    title: str
    owasp: str
    description: str
    safe_behaviour: str  # the general rule, used when a goal gives no more specific one
    styles: tuple[str, ...]
    goals: tuple[Goal, ...]
    ask: str  # what to tell a model that is asked to write more attacks of this kind
    needs_tools: bool = False
    checks: tuple[str, ...] = ("prompt_leak", "no_pii", "no_toxicity")  # the free checks that judge this family

    def seeds(self, count: int, canary: str = "") -> list[Seed]:
        """`count` different attacks, built from the styles and goals in a fixed order (the same call always gives
        the same attacks, so a pack can be rebuilt). The pairs are walked diagonally so neighbours differ."""
        seeds: list[Seed] = []
        total = len(self.styles) * len(self.goals)
        for index in range(min(count, total)):
            style = self.styles[index % len(self.styles)]
            goal = self.goals[(index + index // len(self.styles)) % len(self.goals)]
            seeds.append(
                Seed(style.format(goal=goal.text, canary=canary), f"{self.safe_behaviour} {goal.safe}".strip())
            )
        return seeds


ATTACKS: Registry[AttackGenerator] = Registry("attack family")
