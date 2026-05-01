import re
from dataclasses import dataclass
from typing import Literal

WordStatus = Literal["match", "substitution", "omission", "insertion"]


@dataclass(frozen=True)
class AlignmentItem:
    target_word: str | None
    spoken_word: str | None
    status: WordStatus


def score_accuracy(target_text: str, transcript: str) -> dict:
    target_words = tokenize(target_text)
    spoken_words = tokenize(transcript)
    alignment = align_words(target_words, spoken_words)

    counts = {
        "match": 0,
        "substitution": 0,
        "omission": 0,
        "insertion": 0,
    }

    for item in alignment:
        counts[item.status] += 1

    target_count = len(target_words)
    penalty = (
        counts["substitution"] + counts["omission"] + (0.5 * counts["insertion"])
    )
    score = 0 if target_count == 0 else max(0, round(100 * (1 - penalty / target_count)))

    return {
        "accuracy": score,
        "metrics": {
            "target_word_count": target_count,
            "spoken_word_count": len(spoken_words),
            "match_count": counts["match"],
            "substitution_count": counts["substitution"],
            "omission_count": counts["omission"],
            "insertion_count": counts["insertion"],
        },
        "word_feedback": [
            {
                "target_word": item.target_word,
                "spoken_word": item.spoken_word,
                "status": item.status,
            }
            for item in alignment
        ],
        "explanation": build_accuracy_explanation(score, counts),
    }


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    normalized = re.sub(r"['’]", "", normalized)
    return re.findall(r"[a-z0-9]+", normalized)


def align_words(target_words: list[str], spoken_words: list[str]) -> list[AlignmentItem]:
    target_len = len(target_words)
    spoken_len = len(spoken_words)
    costs = [[0] * (spoken_len + 1) for _ in range(target_len + 1)]

    for target_index in range(1, target_len + 1):
        costs[target_index][0] = target_index

    for spoken_index in range(1, spoken_len + 1):
        costs[0][spoken_index] = spoken_index

    for target_index in range(1, target_len + 1):
        for spoken_index in range(1, spoken_len + 1):
            substitution_cost = (
                0
                if target_words[target_index - 1] == spoken_words[spoken_index - 1]
                else 1
            )
            costs[target_index][spoken_index] = min(
                costs[target_index - 1][spoken_index] + 1,
                costs[target_index][spoken_index - 1] + 1,
                costs[target_index - 1][spoken_index - 1] + substitution_cost,
            )

    alignment: list[AlignmentItem] = []
    target_index = target_len
    spoken_index = spoken_len

    while target_index > 0 or spoken_index > 0:
        if target_index > 0 and spoken_index > 0:
            target_word = target_words[target_index - 1]
            spoken_word = spoken_words[spoken_index - 1]
            substitution_cost = 0 if target_word == spoken_word else 1

            if (
                costs[target_index][spoken_index]
                == costs[target_index - 1][spoken_index - 1] + substitution_cost
            ):
                alignment.append(
                    AlignmentItem(
                        target_word=target_word,
                        spoken_word=spoken_word,
                        status="match" if substitution_cost == 0 else "substitution",
                    )
                )
                target_index -= 1
                spoken_index -= 1
                continue

        if (
            target_index > 0
            and costs[target_index][spoken_index]
            == costs[target_index - 1][spoken_index] + 1
        ):
            alignment.append(
                AlignmentItem(
                    target_word=target_words[target_index - 1],
                    spoken_word=None,
                    status="omission",
                )
            )
            target_index -= 1
            continue

        alignment.append(
            AlignmentItem(
                target_word=None,
                spoken_word=spoken_words[spoken_index - 1],
                status="insertion",
            )
        )
        spoken_index -= 1

    alignment.reverse()
    return alignment


def build_accuracy_explanation(score: int, counts: dict[str, int]) -> str:
    if score >= 90:
        return "Strong lexical match with the target sentence."

    issues = []

    if counts["substitution"]:
        issues.append(f"{counts['substitution']} substituted")

    if counts["omission"]:
        issues.append(f"{counts['omission']} omitted")

    if counts["insertion"]:
        issues.append(f"{counts['insertion']} extra")

    if not issues:
        return "No spoken words were matched against the target sentence."

    return f"Accuracy reduced due to {', '.join(issues)} word(s)."
