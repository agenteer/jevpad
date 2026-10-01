"""Build the fixed BANKING77 sample: 1 training example per label (development)
and 2 test examples per label (held-out evaluation).

The selection depends only on the pinned files and the seed, never on model output.
Run once; the manifest is then frozen and hashed.
"""
import csv
import hashlib
import json
import random
from pathlib import Path

SEED = 20260924
DEV_PER_LABEL = 1
TEST_PER_LABEL = 2
DATA = Path(__file__).parent / "data"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(name: str) -> list[dict]:
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return [
            {"source_file": name, "row_index": i, "text": r["text"], "label": r["category"]}
            for i, r in enumerate(csv.DictReader(f))
        ]


def pick(rows: list[dict], per_label: int, rng: random.Random, split: str) -> list[dict]:
    by_label: dict[str, list[dict]] = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    chosen = []
    for label in sorted(by_label):
        for r in rng.sample(by_label[label], per_label):
            chosen.append({**r, "split": split, "text_sha256": sha(r["text"])})
    return chosen


def main() -> None:
    labels = json.loads((DATA / "categories.json").read_text())
    rng = random.Random(SEED)
    dev = pick(load("train.csv"), DEV_PER_LABEL, rng, "dev")
    test = pick(load("test.csv"), TEST_PER_LABEL, rng, "test")

    # Exact-duplicate checks: within the test sample, and between dev and test.
    test_hashes = [r["text_sha256"] for r in test]
    assert len(set(test_hashes)) == len(test_hashes), "duplicate text inside test sample"
    overlap = set(test_hashes) & {r["text_sha256"] for r in dev}
    assert not overlap, f"dev/test overlap: {overlap}"

    for i, r in enumerate(dev):
        r["example_id"] = f"dev-{i:03d}"
    for i, r in enumerate(test):
        r["example_id"] = f"test-{i:03d}"

    manifest = {
        "dataset": "BANKING77 (Casanueva et al., 2020)",
        "source": "https://github.com/PolyAI-LDN/task-specific-datasets",
        "commit": "57ec275d8078af65b7731c2a98be812d844a6d6b",
        "license": "CC-BY-4.0",
        "file_sha256": dict(
            line.split()[::-1] for line in (DATA / "SHA256SUMS").read_text().splitlines()
        ),
        "seed": SEED,
        "selection": f"stratified: {DEV_PER_LABEL} per label from train.csv (dev), "
        f"{TEST_PER_LABEL} per label from test.csv (test); labels iterated in sorted order, "
        "random.Random(seed).sample within each label",
        "labels": labels,
        "counts": {"dev": len(dev), "test": len(test)},
        "examples": dev + test,
    }
    out = Path(__file__).parent / "manifest.json"
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"dev={len(dev)} test={len(test)} labels={len(labels)} -> {out.name} sha256={sha(out.read_text())}")


if __name__ == "__main__":
    main()
