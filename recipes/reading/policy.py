# The rules for the reading list. They only label: every article stays in every reader's list, sorted by
# relevance, and how far down to read is the reader's choice. Nothing is ever removed here.
#
# The four labels are the relevance Score's own four levels (recipes/reading/preferences.yaml),
# found by rounding the score to the nearest level: 3, 2, 1 or 0.
LABELS = (
    (2.5, "Most relevant"),      # rounds to 3
    (1.5, "Relevant"),           # rounds to 2
    (0.5, "Slightly relevant"),  # rounds to 1
)
LOWEST = "Not relevant"          # rounds to 0
# The same four words start each level's description in preferences.yaml, so Jev sees the words readers see.


def relevance_label(score: float) -> str:
    for threshold, label in LABELS:
        if score >= threshold:
            return label
    return LOWEST
