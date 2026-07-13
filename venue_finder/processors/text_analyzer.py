from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Any

from venue_finder.core.models import Venue
from venue_finder.processors.feature_extractor import normalize_quiet_time


PARTY_KEYWORDS = {
    "party": 18,
    "feier": 18,
    "eventlocation": 10,
    "gruppenhaus": 8,
    "partyhaus": 18,
    "dj": 10,
    "music": 8,
    "musik": 8,
    "bbq": 10,
    "grill": 8,
    "camping": 15,
    "zelten": 15,
    "alleinlage": 12,
    "private": 10,
    "privat": 10,
}

NEGATIVE_KEYWORDS = {
    "quiet hours": -25,
    "nachtruhe": -25,
    "noise restriction": -20,
    "loud music not allowed": -35,
    "keine musik": -30,
    "no parties": -50,
    "parties not allowed": -50,
    "nicht erlaubt": -25,
}

QUIET_HOURS_PATTERN = re.compile(
    r"(?:nachtruhe|quiet hours?|ruhe|silent hours?)"
    r"(?:\s*(?:ab|from|starting at|von)?\s*)?"
    r"(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))?\s*(?:uhr|pm|am)?",
    re.IGNORECASE,
)

TIME_RANGE_PATTERN = re.compile(
    r"(?P<start>\d{1,2})(?:[:.](?P<start_minute>\d{2}))?\s*(?:uhr)?\s*(?:-|bis|to|until|and)\s*"
    r"(?P<end>\d{1,2})(?:[:.](?P<end_minute>\d{2}))?\s*(?:uhr)?",
    re.IGNORECASE,
)


@dataclass(slots=True)
class VenueAnalysis:
    suitable_for_party: bool
    camping_possible: bool
    noise_restrictions: bool
    private_venue: bool
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    party_score: int
    suitability_summary: str
    restrictions_summary: str
    signals: dict[str, Any] = field(default_factory=dict)


class TextAnalyzer:
    def __init__(self, openai_api_key: str | None = None) -> None:
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

    def analyze(self, text: str, venue: Venue | None = None) -> VenueAnalysis:
        clean_text = text or ""
        lower = clean_text.lower()

        score = 0
        positive_signals: list[str] = []
        negative_signals: list[str] = []

        for keyword, points in PARTY_KEYWORDS.items():
            if keyword in lower:
                score += points
                positive_signals.append(keyword)

        for keyword, points in NEGATIVE_KEYWORDS.items():
            if keyword in lower:
                score += points
                negative_signals.append(keyword)

        camping_possible = any(term in lower for term in ("camping", "zelten", "camp", "camper"))
        private_venue = any(term in lower for term in ("private", "privat", "alleinlage", "exklusiv"))
        noise_restrictions = any(term in lower for term in ("nachtruhe", "quiet hours", "loud music not allowed", "no music", "ruhe"))

        quiet_hours_start = venue.quiet_hours_start if venue is not None else None
        quiet_hours_end = venue.quiet_hours_end if venue is not None else None
        parsed_quiet_hour = self._extract_quiet_hours(lower)
        if parsed_quiet_hour is not None and quiet_hours_start is None:
            quiet_hours_start = parsed_quiet_hour
            noise_restrictions = True

        if venue is not None:
            if venue.private_property:
                score += 25
                positive_signals.append("private_property")
            if venue.camping_allowed:
                score += 20
                camping_possible = True
            if venue.maximum_guests is not None and venue.maximum_guests >= 50:
                score += 15
            if venue.bbq_available:
                score += 10
            if venue.dj_allowed or venue.sound_system_available:
                score += 10
            if venue.loud_music_allowed:
                score += 20
            if quiet_hours_start is not None:
                start_minutes = self._time_to_minutes(quiet_hours_start)
                if start_minutes is not None and start_minutes <= 22 * 60:
                    score -= 20
                    noise_restrictions = True
                if start_minutes is not None and start_minutes < 21 * 60:
                    score -= 10
            if quiet_hours_end is not None:
                end_minutes = self._time_to_minutes(quiet_hours_end)
                if end_minutes is not None and end_minutes >= 7 * 60:
                    score -= 5

        score = max(0, min(100, score))
        suitable_for_party = score >= 50 and not any(term in lower for term in ("no parties", "parties not allowed", "nicht erlaubt"))
        suitability_summary = self._build_summary(suitable_for_party, camping_possible, private_venue, positive_signals)
        restrictions_summary = self._build_restrictions_summary(noise_restrictions, negative_signals)

        return VenueAnalysis(
            suitable_for_party=suitable_for_party,
            camping_possible=camping_possible,
            noise_restrictions=noise_restrictions,
            private_venue=private_venue,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            party_score=score,
            suitability_summary=suitability_summary,
            restrictions_summary=restrictions_summary,
            signals={"positive": positive_signals, "negative": negative_signals},
        )

    def _build_summary(self, suitable: bool, camping: bool, private_venue: bool, signals: list[str]) -> str:
        phrases = [
            "Likely suitable for parties" if suitable else "Not clearly suitable for parties",
            "camping appears possible" if camping else "camping is not clearly mentioned",
            "private venue signals detected" if private_venue else "privacy is unclear",
        ]
        if signals:
            phrases.append(f"signals: {', '.join(signals[:6])}")
        return ". ".join(phrases)

    def _build_restrictions_summary(self, noise_restrictions: bool, negative_signals: list[str]) -> str:
        phrases = ["Noise restrictions appear present" if noise_restrictions else "No strong noise restriction signal found"]
        if negative_signals:
            phrases.append(f"negatives: {', '.join(negative_signals[:6])}")
        return ". ".join(phrases)

    def _extract_quiet_hours(self, text: str) -> str | None:
        match = QUIET_HOURS_PATTERN.search(text)
        if match:
            hour = int(match.group("hour"))
            minute = int(match.group("minute") or "00")
            return normalize_quiet_time(f"{hour:02d}:{minute:02d}")

        match = TIME_RANGE_PATTERN.search(text)
        if match:
            hour = int(match.group("start"))
            minute = int(match.group("start_minute") or "00")
            return normalize_quiet_time(f"{hour:02d}:{minute:02d}")
        return None

    def _time_to_minutes(self, value: str | None) -> int | None:
        if not value:
            return None
        try:
            hour_str, minute_str = value.split(":", 1)
            normalized = normalize_quiet_time(f"{hour_str}:{minute_str}")
            if normalized is None:
                return None
            hour_str, minute_str = normalized.split(":", 1)
            return int(hour_str) * 60 + int(minute_str)
        except Exception:
            return None

    def analyze_with_openai(self, text: str) -> dict[str, Any] | None:
        try:
            from openai import OpenAI
        except Exception:
            return None

        if not self.openai_api_key:
            return None

        client = OpenAI(api_key=self.openai_api_key)
        prompt = (
            "Analyze this venue description for party suitability, camping possibility, noise restrictions, "
            "and whether it seems private. Return JSON with keys suitable_for_party, camping_possible, "
            "noise_restrictions, private_venue, party_score, summary, restrictions_summary."
        )
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            return None
        return {"raw": output_text}
