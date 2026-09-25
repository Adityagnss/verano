"""
Make Verano's image builds work offline once the base images have been fetched.

Verano builds on a dedicated docker-container builder (its cache is kept apart from other
projects), but such a builder cannot see Docker Desktop's local image store and asks
Docker Hub for every base image on every build. This script:

1. `export` (default): for each digest-pinned image in infra/base-images.lock that is not
   already in .cache/base-images/, has the builder export it as a local OCI layout. This is
   the only step that needs the network, and it runs once per base image version.
2. writes .cache/base-images/compose.override.yml, which points every `FROM <tag>` in the
   Dockerfiles used by docker-compose.yml at its local layout, so Compose builds never
   contact a registry.

A Dockerfile base image missing from the lock file is an error, so the lock stays complete.
Run through `make base-images`, which every build target depends on.
"""

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "infra/base-images.lock"
CACHE = ROOT / ".cache/base-images"
OVERRIDE = CACHE / "compose.override.yml"
COMPOSE = ROOT / "docker-compose.yml"
BUILDER = "verano"
FROM = re.compile(r"^FROM\s+(\S+)", re.MULTILINE)


def pinned() -> dict[str, str]:
    lines = [line.strip() for line in LOCK.read_text().splitlines() if line.strip() and not line.startswith("#")]
    return {line.split("@", 1)[0]: line for line in lines}


def layout_dir(tag: str) -> Path:
    return CACHE / re.sub(r"[/:]", "_", tag)


def export(tag: str, reference: str) -> None:
    target = layout_dir(tag)
    if (target / "index.json").exists():
        return
    print(f"Fetching base image {reference} once (needs Docker Hub)...")
    dockerfile = f"FROM {reference}\n"
    command = ["docker", "buildx", "build", "--builder", BUILDER, "-q", "-o", f"type=oci,tar=false,dest={target}", "-"]
    subprocess.run(command, input=dockerfile, text=True, check=True, stdout=subprocess.DEVNULL)


def dockerfile_bases(dockerfile: Path) -> list[str]:
    return sorted({ref for ref in FROM.findall(dockerfile.read_text()) if ":" in ref})


def override(locked: dict[str, str]) -> dict[str, object]:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    result: dict[str, object] = {}
    for name, spec in services.items():
        build = spec.get("build")
        if not build:
            continue
        dockerfile = (ROOT / build["context"] / build["dockerfile"]).resolve()
        bases = dockerfile_bases(dockerfile)
        missing = [tag for tag in bases if tag not in locked]
        if missing:
            raise SystemExit(f"{dockerfile.name} uses base images missing from {LOCK.name}: {', '.join(missing)}")
        contexts = {tag: f"oci-layout://{layout_dir(tag)}" for tag in bases}
        result[name] = {"build": {"additional_contexts": contexts}}
    return {"services": result}


def main() -> int:
    locked = pinned()
    CACHE.mkdir(parents=True, exist_ok=True)
    for tag, reference in locked.items():
        export(tag, reference)
    OVERRIDE.write_text(yaml.safe_dump(override(locked), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
