"""Check credential selection using synthetic values and temporary files only."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_comparison_v2 as front


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(front.os, "environ", {})
    monkeypatch.setattr(front.runner, "HERE", tmp_path / "comparison")
    return tmp_path / ".env"


def test_environment_precedes_dotenv(isolated, monkeypatch):
    front.os.environ["AI_GATEWAY_API_KEY"] = "synthetic-environment-value"

    def unexpected_read(*args, **kwargs):
        pytest.fail("The environment must avoid any dotenv read")

    monkeypatch.setattr(Path, "read_text", unexpected_read)
    front.load_key()
    assert front.os.environ["AI_GATEWAY_API_KEY"] == "synthetic-environment-value"


def test_repository_dotenv_only_loads_named_variable(isolated, monkeypatch):
    isolated.write_text('OTHER=$(ignored)\nexport AI_GATEWAY_API_KEY="synthetic-file-value" # comment\n')
    monkeypatch.chdir(isolated.parent.parent)
    before = dict(front.os.environ)
    front.load_key()
    assert front.os.environ == {**before, "AI_GATEWAY_API_KEY": "synthetic-file-value"}


def test_dotenv_does_not_evaluate_shell(isolated):
    marker = isolated.parent / "unexpected-execution"
    literal = f"$(touch {marker})"
    isolated.write_text(f"AI_GATEWAY_API_KEY='{literal}'\n")
    front.load_key()
    assert front.os.environ["AI_GATEWAY_API_KEY"] == literal
    assert not marker.exists()


@pytest.mark.parametrize("contents", [None, "OTHER=ignored\n"])
def test_missing_key_has_viewer_message(isolated, contents):
    if contents is not None:
        isolated.write_text(contents)
    with pytest.raises(SystemExit) as exc:
        front.load_key()
    assert str(exc.value) == (
        "Set AI_GATEWAY_API_KEY in your environment or in .env at the repository root."
    )


@pytest.mark.parametrize("value", ["", "one two", "'unclosed"])
def test_invalid_entry_does_not_expose_value(isolated, value):
    isolated.write_text(f"AI_GATEWAY_API_KEY={value}\n")
    before = dict(front.os.environ)
    with pytest.raises(SystemExit) as exc:
        front.load_key()
    assert str(exc.value) == "Invalid AI_GATEWAY_API_KEY entry in repository .env"
    assert front.os.environ == before


def test_check_never_loads_credentials(isolated, monkeypatch, capsys):
    monkeypatch.setattr(front.runner, "check_frozen", lambda: None)

    def unexpected_load():
        pytest.fail("The frozen check must not load credentials")

    monkeypatch.setattr(front, "load_key", unexpected_load)
    front.main(["--check"])
    assert capsys.readouterr().out == "Frozen settings: OK\n"
