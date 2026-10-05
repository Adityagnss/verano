"""Server addresses and the saved sign-in."""

import os
import stat
import sys
from pathlib import Path

import pytest

from verano.config import (
    Credentials,
    credentials_path,
    delete_credentials,
    load_credentials,
    normalize_url,
    save_credentials,
)
from verano.errors import CliError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:8080", "http://localhost:8080"),
        ("http://localhost:8080/", "http://localhost:8080"),
        ("  https://verano.example.com/api/v1/ ", "https://verano.example.com"),
        ("https://verano.example.com/api/v1", "https://verano.example.com"),
    ],
)
def test_addresses_are_tidied(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["localhost:8080", "ftp://example.com", "http://", "http:///x", "", "example.com"])
def test_things_that_are_not_server_addresses_are_refused_with_an_example(raw: str) -> None:
    with pytest.raises(CliError) as error:
        normalize_url(raw)
    assert error.value.hint is not None
    assert "http" in error.value.hint


def test_the_saved_sign_in_round_trips_and_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert load_credentials(env) is None
    path = save_credentials(Credentials("http://x.test", "vrn_secret", "ada@example.com", "tok-1"), env)
    assert path == credentials_path(env)
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    loaded = load_credentials(env)
    assert loaded == Credentials("http://x.test", "vrn_secret", "ada@example.com", "tok-1", "file")
    assert delete_credentials(env) is True
    assert delete_credentials(env) is False


def test_saving_again_keeps_the_file_private_even_if_it_was_loosened(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    path = save_credentials(Credentials("http://x.test", "vrn_one"), env)
    path.chmod(0o644)
    save_credentials(Credentials("http://x.test", "vrn_two"), env)
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    loaded = load_credentials(env)
    assert loaded is not None
    assert loaded.token == "vrn_two"


def test_environment_variables_win_over_the_file_so_ci_needs_no_login(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    save_credentials(Credentials("http://file.test", "vrn_file"), env)
    ci = load_credentials({**env, "VERANO_API_TOKEN": " vrn_ci ", "VERANO_URL": "https://ci.test/"})
    assert ci == Credentials("https://ci.test", "vrn_ci", source="environment")
    default = load_credentials({**env, "VERANO_API_TOKEN": "vrn_ci"})
    assert default is not None
    assert default.url == "http://localhost:8080"
    override = load_credentials({**env, "VERANO_URL": "http://other.test"})
    assert override is not None
    assert (override.url, override.token) == ("http://other.test", "vrn_file")


@pytest.mark.parametrize("content", ["not json", "{}", '{"url": "http://x.test"}', "[]"])
def test_an_unreadable_saved_sign_in_says_what_to_do(tmp_path: Path, content: str) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    path = credentials_path(env)
    path.parent.mkdir(parents=True)
    path.write_text(content)
    with pytest.raises(CliError) as error:
        load_credentials(env)
    assert error.value.hint == "Run `verano login` again."
