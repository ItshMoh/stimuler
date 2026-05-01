import re
from dataclasses import dataclass
from statistics import pstdev
from typing import Any
from typing import Literal

WordStatus = Literal["match", "substitution", "omission", "insertion"]
FILLER_WORDS = {"um", "uh", "erm", "hmm", "like", "actually", "oh"}
MILD_PAUSE_SECONDS = 0.7
AWKWARD_PAUSE_SECONDS = 1.2


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


def score_delivery(words: list[dict[str, Any]]) -> dict:
    timed_words = [word for word in words if _has_timing(word)]
    filler_events = detect_fillers(words)
    pauses = detect_pauses(timed_words)
    words_per_minute = calculate_words_per_minute(timed_words)

    filler_score = max(0, 100 - (len(filler_events) * 12))
    pause_score = max(
        0,
        100
        - (len([pause for pause in pauses if pause["type"] == "mild_hesitation"]) * 8)
        - (len([pause for pause in pauses if pause["type"] == "awkward_pause"]) * 18),
    )
    pace_score = calculate_pace_score(words_per_minute)
    rhythm_score = calculate_rhythm_score(pauses)
    fluency_score = round(
        (pace_score * 0.35)
        + (pause_score * 0.3)
        + (filler_score * 0.2)
        + (rhythm_score * 0.15)
    )

    return {
        "scores": {
            "fluency": fluency_score,
            "pause": pause_score,
            "filler": filler_score,
        },
        "metrics": {
            "words_per_minute": words_per_minute,
            "speaking_duration_seconds": calculate_speaking_duration(timed_words),
            "filler_count": len(filler_events),
            "pause_count": len(pauses),
            "awkward_pause_count": len(
                [pause for pause in pauses if pause["type"] == "awkward_pause"]
            ),
            "mild_hesitation_count": len(
                [pause for pause in pauses if pause["type"] == "mild_hesitation"]
            ),
            "rhythm_score": rhythm_score,
        },
        "fillers": filler_events,
        "pauses": pauses,
        "explanation": build_delivery_explanation(
            fluency_score=fluency_score,
            words_per_minute=words_per_minute,
            filler_count=len(filler_events),
            awkward_pause_count=len(
                [pause for pause in pauses if pause["type"] == "awkward_pause"]
            ),
        ),
    }


def calculate_words_per_minute(words: list[dict[str, Any]]) -> int | None:
    duration = calculate_speaking_duration(words)

    if duration is None or duration <= 0:
        return None

    return round((len(words) / duration) * 60)


def calculate_speaking_duration(words: list[dict[str, Any]]) -> float | None:
    if not words:
        return None

    first_start = words[0]["start"]
    last_end = words[-1]["end"]

    if first_start is None or last_end is None or last_end <= first_start:
        return None

    return round(last_end - first_start, 2)


def detect_fillers(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fillers: list[dict[str, Any]] = []

    for index, word in enumerate(words):
        normalized = normalize_word(word.get("word", ""))

        if normalized in FILLER_WORDS:
            fillers.append(_format_filler(word, normalized))
            continue

        if normalized == "you" and index + 1 < len(words):
            next_word = normalize_word(words[index + 1].get("word", ""))

            if next_word == "know":
                fillers.append(
                    {
                        "word": "you know",
                        "start": word.get("start"),
                        "end": words[index + 1].get("end"),
                    }
                )

    return fillers


def detect_pauses(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pauses: list[dict[str, Any]] = []

    for previous_word, next_word in zip(words, words[1:]):
        gap = round(next_word["start"] - previous_word["end"], 2)

        if gap < MILD_PAUSE_SECONDS:
            continue

        pause_type = (
            "awkward_pause" if gap >= AWKWARD_PAUSE_SECONDS else "mild_hesitation"
        )
        pauses.append(
            {
                "type": pause_type,
                "duration_seconds": gap,
                "after_word": previous_word.get("word", ""),
                "before_word": next_word.get("word", ""),
                "start": previous_word.get("end"),
                "end": next_word.get("start"),
            }
        )

    return pauses


def calculate_pace_score(words_per_minute: int | None) -> int:
    if words_per_minute is None:
        return 0

    if 110 <= words_per_minute <= 160:
        return 100

    if words_per_minute < 110:
        return max(0, round(100 - ((110 - words_per_minute) * 1.6)))

    return max(0, round(100 - ((words_per_minute - 160) * 1.2)))


def calculate_rhythm_score(pauses: list[dict[str, Any]]) -> int:
    if len(pauses) < 2:
        return 100

    durations = [pause["duration_seconds"] for pause in pauses]
    spread = pstdev(durations)
    return max(0, round(100 - (spread * 45)))


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    normalized = re.sub(r"['’]", "", normalized)
    return re.findall(r"[a-z0-9]+", normalized)


def normalize_word(word: str) -> str:
    normalized = word.lower()
    normalized = re.sub(r"['’]", "", normalized)
    match = re.search(r"[a-z0-9]+", normalized)
    return match.group(0) if match else ""


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


def build_delivery_explanation(
    *,
    fluency_score: int,
    words_per_minute: int | None,
    filler_count: int,
    awkward_pause_count: int,
) -> str:
    if fluency_score >= 90:
        return "Speech pace, pauses, and filler use were controlled."

    issues = []

    if words_per_minute is None:
        issues.append("word timing was unavailable")
    elif words_per_minute < 110:
        issues.append("pace was slower than the target range")
    elif words_per_minute > 160:
        issues.append("pace was faster than the target range")

    if awkward_pause_count:
        issues.append(f"{awkward_pause_count} awkward pause(s)")

    if filler_count:
        issues.append(f"{filler_count} filler word(s)")

    if not issues:
        return "Fluency was reduced by uneven delivery."

    return f"Fluency reduced because {', '.join(issues)}."


def _has_timing(word: dict[str, Any]) -> bool:
    return isinstance(word.get("start"), (int, float)) and isinstance(
        word.get("end"), (int, float)
    )


def _format_filler(word: dict[str, Any], normalized: str) -> dict[str, Any]:
    return {
        "word": normalized,
        "start": word.get("start"),
        "end": word.get("end"),
    }
