"""A project's traffic choices: the stored row when there is one, otherwise the server's defaults."""

import uuid
from typing import Any

from app.core.config import Settings
from app.modules.traffic.domain import ScrubConfig
from app.modules.traffic.models import TrafficConfig
from app.modules.traffic.schemas import ConfigOut

FIELDS = (
    "scrub_pii",
    "scrub_emails",
    "scrub_phones",
    "scrub_cards",
    "scrub_patterns",
    "retention_days",
    "scoring_enabled",
    "rule_sample_rate",
    "judge_sample_rate",
    "judge_monthly_limit",
)


def default_values(settings: Settings) -> dict[str, Any]:
    return {
        "scrub_pii": settings.traffic_scrub_pii,
        "scrub_emails": True,
        "scrub_phones": True,
        "scrub_cards": True,
        "scrub_patterns": [],
        "retention_days": settings.traffic_retention_days,
        "scoring_enabled": False,
        "rule_sample_rate": settings.traffic_rule_sample_rate,
        "judge_sample_rate": settings.traffic_judge_sample_rate,
        "judge_monthly_limit": settings.traffic_judge_monthly_limit,
    }


def effective_config(row: TrafficConfig | None, settings: Settings) -> ConfigOut:
    values = default_values(settings)
    if row is not None:
        values = {name: getattr(row, name) for name in FIELDS}
    values["scrub_patterns"] = [str(p) for p in values["scrub_patterns"]]
    return ConfigOut(**values)


def new_row(project_id: uuid.UUID, values: dict[str, Any]) -> TrafficConfig:
    return TrafficConfig(project_id=project_id, **values)


def scrub_of(config: ConfigOut) -> ScrubConfig:
    return ScrubConfig(
        enabled=config.scrub_pii,
        emails=config.scrub_emails,
        phones=config.scrub_phones,
        cards=config.scrub_cards,
        patterns=tuple(config.scrub_patterns),
    )
