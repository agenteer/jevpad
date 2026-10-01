"""Offline tests for the personal reading list: every reader in data/readers.csv × every Academy article."""
import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest
from rich.console import Console

import jevpad.cli as cli
import jevpad.evidence as evidence_module
import jevpad.export as export_module
import jevpad.modes as modes
import jevpad.recipes as recipes
from jevpad.config import Settings
from jevpad.jev import build_questions, load_yaml
from recipes.reading.policy import relevance_label


COMPANION = Path(__file__).resolve().parents[1]
ARTICLES = COMPANION / "data/academy-articles.csv"
READERS = COMPANION / "data/readers.csv"
PAIR = ("dental_office", "support_developer")


def settings() -> Settings:
    return Settings(
        typesafe_key_present=False, typesafe_base_url=None, typesafe_model="jev-test",
        pin_provider=None, fault=None,
    )


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(export_module, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "load_settings", settings)
    monkeypatch.setattr(cli, "console", Console(width=400))
    monkeypatch.setattr(recipes, "console", Console(width=400))
    return tmp_path


def reading(monkeypatch, *args: str) -> int:
    monkeypatch.setattr("sys.argv", ["jevpad", "reading", *args])
    return cli.main()


def rows_of(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def evidence(tmp_path: Path) -> list[dict]:
    return [json.loads(line) for source in (tmp_path / "runs").glob("*.jsonl") for line in source.read_text().splitlines()]


def test_academy_data_is_metadata_only():
    rows = rows_of(ARTICLES)
    assert len(rows) == 15
    assert list(rows[0]) == ["id", "title", "description", "url", "academy_path"]
    assert {row["academy_path"] for row in rows} == {"business", "engineering", "both"}
    for row in rows:
        assert row["url"].startswith("https://agenteer.com/") and row["url"].endswith(f"/{row['id']}/")
        assert row["title"] and row["description"]
        assert len(row["description"]) < 400  # a frontmatter description, never an article body


def test_readers_file_and_fixtures_cover_every_reader_and_article():
    readers = rows_of(READERS)
    assert list(readers[0]) == ["id", "description"] and len(readers) == 10
    assert all(reader["description"].startswith("I") for reader in readers)  # first person
    article_ids = {row["id"] for row in rows_of(ARTICLES)}
    assert set(modes.READING_FIXTURES) == {reader["id"] for reader in readers}
    for answers in modes.READING_FIXTURES.values():
        assert set(answers) == article_ids


def test_one_shared_question_set_for_every_reader():
    questions = load_yaml(COMPANION / "recipes/reading/preferences.yaml")
    assert set(questions) == {"questions"}  # no per-reader rubrics
    assert set(build_questions(questions["questions"])) == {"relevance", "opinion_or_overview"}
    assert len(questions["questions"]["relevance"]["levels"]) == 4


def test_default_run_scores_every_reader_and_shows_top_picks(offline, monkeypatch, capsys):
    assert reading(monkeypatch, "--mode", "fixture", "--export", "--html", "out/reading.html") == 0
    output = capsys.readouterr().out
    assert "=== FIXTURE · NOT MODEL OUTPUT ===" in output
    assert "each reader's top 3 articles by relevance" in output
    assert "Reader (in their own words)" in output
    assert "“I run a five-person dental office." in output and "Reader: dental_office" in output
    assert "1. Why Voice AI Agents Are No Longer Optional: A Practical Guide for Small Business Owners · 2.93 · Most relevant" in output
    assert "KEEP" not in output and "EXCLUDE" not in output and "Kept" not in output

    rows = json.loads((offline / "out/reading.json").read_text())
    assert len(rows) == 150
    by_key = {(row["reader"], row["id"]): row for row in rows}
    top = by_key[("dental_office", "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners")]
    assert top["rank"] == 1 and top["label"] == "Most relevant" and top["site_academy_path"] == "business"
    assert all("action" not in row for row in rows)
    assert top["opinion_or_overview"] == 0.55
    assert by_key[("support_developer", "hermes-agent-ai-customer-support-team")]["rank"] == 1
    header = (offline / "out/reading.csv").read_text().splitlines()[0].split(",")
    assert {"reader", "relevance", "label", "rank", "opinion_or_overview", "site_academy_path"} <= set(header)
    assert "action" not in header

    report = (offline / "out/reading.html").read_text()
    assert report.count("<h2 id=") == 10
    assert "<h2 id='dental_office'>“I run a five-person dental office." in report
    assert "<p class='note'>Reader: dental_office</p>" in report
    assert "KEEP" not in report and "EXCLUDE" not in report
    assert "The site's own label (not Jev's)" in report
    assert "href='https://agenteer.com/blog/loop-engineering/'" in report

    records = evidence(offline)
    assert len(records) == 150
    assert all(set(record["state"]) == {"reader", "title", "description"} for record in records)
    assert all("academy_path" not in json.dumps(record["state"]) for record in records)


def test_reader_option_takes_repeats_and_comma_lists(offline, monkeypatch, capsys):
    assert reading(monkeypatch, "--reader", "dental_office,ops_lead", "--reader", "student", "--mode", "fixture",
                   "--export") == 0
    rows = json.loads((offline / "out/reading.json").read_text())
    assert [row["reader"] for row in rows[::15]] == ["dental_office", "ops_lead", "student"]
    assert reading(monkeypatch, "--reader", "nobody", "--mode", "fixture") == 2
    assert "unknown reader nobody; readers in the file: dental_office" in capsys.readouterr().out


def test_one_reader_also_prints_their_full_ranked_list(offline, monkeypatch, capsys):
    assert reading(monkeypatch, "--reader", "dental_office", "--mode", "fixture") == 0
    output = capsys.readouterr().out
    assert "Reading list for “I run a five-person dental office." in output
    assert "opinion/overview=" in output and "Not relevant" in output and "Slightly relevant" in output


def test_compare_two_readers(offline, monkeypatch, capsys):
    assert reading(monkeypatch, "--compare", *PAIR, "--mode", "fixture", "--export", "--html", "out/reading-compare.html") == 0
    output = capsys.readouterr().out
    assert "Reading list — same articles, two readers" in output
    assert "Site's path" in output and "not Jev)" in output
    assert len(json.loads((offline / "out/reading.json").read_text())) == 30
    assert reading(monkeypatch, "--compare", "student", "student", "--mode", "fixture") == 2
    assert "--compare needs two different readers" in capsys.readouterr().out


def test_overview_answer_never_changes_label_or_rank(offline, monkeypatch):
    def run() -> list[tuple[str, str, int, str]]:
        rows, status = recipes.run_reading(settings=settings(), mode="fixture")
        assert status == 0
        return sorted((row["reader"], row["id"], row["rank"], row["label"]) for row in rows)

    before = run()
    flipped = {reader: {key: (score, conf, 1 - overview) for key, (score, conf, overview) in answers.items()}
               for reader, answers in modes.READING_FIXTURES.items()}
    monkeypatch.setattr(modes, "READING_FIXTURES", flipped)
    assert run() == before


def test_a_reader_added_to_the_file_runs_live_not_as_a_fixture(offline, monkeypatch, capsys, tmp_path):
    mine = tmp_path / "readers.csv"
    mine.write_text(READERS.read_text(encoding="utf-8") + "me,I teach high-school biology and want classroom ideas.\n",
                    encoding="utf-8")
    monkeypatch.setattr(cli, "load_settings", lambda: replace(settings(), jev_max_retries=0))

    assert reading(monkeypatch, "--readers", str(mine), "--reader", "me", "--mode", "fixture") == 2
    assert "no fixture answers for reader me" in capsys.readouterr().out
    # The live path accepts the new reader; an injected fault proves it without any provider call.
    assert reading(monkeypatch, "--readers", str(mine), "--reader", "me", "--inject-fault", "ratelimit", "--export") == 1
    [row] = json.loads((offline / "out/reading.json").read_text())
    assert row["reader"] == "me" and row["label"] == "FAILED — no answer"
    assert evidence(offline)[0]["state"]["reader"] == "I teach high-school biology and want classroom ideas."


def test_readers_file_rejects_duplicates_and_missing_columns(offline, monkeypatch, capsys, tmp_path):
    duplicate = tmp_path / "dup.csv"
    duplicate.write_text("id,description\nme,One.\nme,Two.\n", encoding="utf-8")
    assert reading(monkeypatch, "--readers", str(duplicate), "--mode", "fixture") == 2
    assert "repeats the id me" in capsys.readouterr().out
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("name,about\nme,One.\n", encoding="utf-8")
    assert reading(monkeypatch, "--readers", str(wrong), "--mode", "fixture") == 2
    assert "must have id,description columns" in capsys.readouterr().out


def test_articles_csv_needs_a_description_column(offline, monkeypatch, capsys, tmp_path):
    source = tmp_path / "old.csv"
    source.write_text("id,title,excerpt\nR01,A title,Some text\n", encoding="utf-8")
    assert reading(monkeypatch, "--reader", "student", "--mode", "fixture", "--input", str(source)) == 2
    assert "reading CSV must have id,title,description columns" in capsys.readouterr().out


def test_labels_round_the_score_to_the_nearest_rubric_level():
    levels = load_yaml(COMPANION / "recipes/reading/preferences.yaml")["questions"]["relevance"]["levels"]
    assert len(levels) == 4
    cases = {3.0: "Most relevant", 2.5: "Most relevant", 2.49: "Relevant", 1.5: "Relevant", 1.49: "Slightly relevant",
             0.5: "Slightly relevant", 0.49: "Not relevant", 0.0: "Not relevant"}
    for score, label in cases.items():
        assert relevance_label(score) == label, score


def test_nothing_is_ever_dropped_from_a_readers_list(offline, monkeypatch):
    rows, status = recipes.run_reading(settings=settings(), mode="fixture")
    assert status == 0
    article_ids = {row["id"] for row in rows_of(ARTICLES)}
    by_reader: dict[str, list[dict]] = {}
    for row in rows:
        by_reader.setdefault(row["reader"], []).append(row)
    assert len(by_reader) == 10
    for reader_rows in by_reader.values():
        assert {row["id"] for row in reader_rows} == article_ids  # every article, however low
        assert [row["rank"] for row in reader_rows] == list(range(1, 16))
        scores = [row["relevance"] for row in reader_rows]
        assert scores == sorted(scores, reverse=True)
        assert all(row["label"] == relevance_label(row["relevance"]) for row in reader_rows)
    assert {row["label"] for row in rows} == {"Most relevant", "Relevant", "Slightly relevant", "Not relevant"}


def test_reading_help_says_every_article_is_listed(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["jevpad", "reading", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    text = " ".join(capsys.readouterr().out.split())
    assert "list every article for each reader, most relevant first" in text
    assert "keep the relevant" not in text
