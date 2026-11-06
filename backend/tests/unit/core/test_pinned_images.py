"""
Guards the rule that image versions are written down once, in docker-compose.yml: every
image is pinned to an exact version, and the hosted CI's service containers use exactly
the Compose images that the test suite and the stack use.
"""

import re

import pytest
import yaml

from tests.helpers import COMPOSE_FILE, ROOT, compose_image

pytestmark = pytest.mark.unit

CI_FILE = ROOT.parent / ".github/workflows/ci.yml"
EXACT_VERSION = re.compile(r":v?\d+\.\d+\.\d+|:\d+\.\d+-")
LOCALLY_BUILT = re.compile(r"^verano-[a-z]+:dev$")


def test_every_compose_image_is_pinned_to_an_exact_version() -> None:
    services = yaml.safe_load(COMPOSE_FILE.read_text())["services"]
    images = {name: spec["image"] for name, spec in services.items() if "image" in spec}
    unpinned = {
        name: image for name, image in images.items() if not (EXACT_VERSION.search(image) or LOCALLY_BUILT.match(image))
    }
    assert unpinned == {}


def test_hosted_ci_service_containers_use_the_compose_images() -> None:
    ci_services = yaml.safe_load(CI_FILE.read_text())["jobs"]["ci"]["services"]
    assert {name: spec["image"] for name, spec in ci_services.items()} == {
        name: compose_image(name) for name in ci_services
    }
