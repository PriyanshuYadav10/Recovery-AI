from __future__ import annotations

import json
import re
from typing import Any, Optional


class FieldExtractor:
    """Deterministic field extraction with optional LLM enrichment."""

    # Below this, a deterministic match is not trusted on its own and the LLM
    # hint is allowed to stand in.
    RULES_TRUSTED_AT = 0.85

    def extract(
        self,
        text: str,
        step: dict[str, Any],
        llm_hint: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Rules first, model second.

        The deterministic matcher is checked before the LLM hint and wins
        whenever it is confident. Letting the hint go first meant a model that
        heard "Both electricity and gas" and answered "electricity" silently
        overrode a correct rule match - the opposite of the guarantee this
        system makes about who owns decisions.
        """
        field_id = step["id"]
        validation = step.get("validation", {})

        rules = self._deterministic(text, step)
        if rules.get("value") is not None and rules.get("confidence", 0) >= self.RULES_TRUSTED_AT:
            if llm_hint and llm_hint.get("field") == field_id:
                hinted = self._normalize(llm_hint.get("value"), validation)
                if hinted is not None and hinted != rules["value"]:
                    # Worth surfacing: the two disagreed and the rules were kept.
                    rules = {**rules, "llm_disagreed_with": hinted}
            return rules

        # Rules found nothing usable - let the model fill the gap, still
        # normalised and validated against the journey definition.
        if llm_hint and llm_hint.get("field") == field_id and llm_hint.get("value") is not None:
            normalized = self._normalize(llm_hint["value"], validation)
            if normalized is not None:
                return {
                    "field": field_id,
                    "value": normalized,
                    "confidence": float(llm_hint.get("confidence", 0.9)),
                    "needs_clarification": bool(llm_hint.get("needs_clarification", False)),
                    "source": "llm+rules",
                }

        return rules

    def _deterministic(self, text: str, step: dict[str, Any]) -> dict[str, Any]:
        field_id = step["id"]
        validation = step.get("validation", {})
        vtype = validation.get("type")
        raw = (text or "").strip()
        lowered = raw.lower()

        if vtype == "regex":
            pattern = validation.get("pattern", ".*")
            m = re.search(pattern, raw)
            if m:
                return {
                    "field": field_id,
                    "value": m.group(0),
                    "confidence": 0.96,
                    "needs_clarification": False,
                    "source": "regex",
                }
            # also try digits for postcode-like
            digits = re.findall(r"\b(\d{4})\b", raw)
            if digits and field_id == "postcode":
                return {
                    "field": field_id,
                    "value": digits[0],
                    "confidence": 0.9,
                    "needs_clarification": False,
                    "source": "regex",
                }
            return self._miss(field_id)

        if vtype == "enum":
            values = validation.get("values", [])
            aliases = validation.get("aliases", {})
            candidates = list(aliases.keys()) + list(values)
            # "house, not apartment" means house - drop what the customer ruled out
            # before looking at what is left.
            searchable = lowered
            for cand in sorted(candidates, key=len, reverse=True):
                searchable = re.sub(
                    rf"\bnot\s+(a\s+|an\s+|the\s+)?{re.escape(cand)}\b",
                    " ",
                    searchable,
                )

            # (length, position) - the longest phrase wins, so "both electricity
            # and gas" reads as "both" rather than the "gas" that trails it; when
            # two matches are the same length the later one wins, which is how a
            # mid-sentence self-correction lands.
            matches: list[tuple[int, int, str, float, str]] = []
            for alias, canonical in aliases.items():
                idx = searchable.rfind(alias)
                if idx >= 0:
                    matches.append((len(alias), idx, canonical, 0.93, "alias"))
            for v in values:
                last = None
                for last in re.finditer(rf"\b{re.escape(v)}\b", searchable):
                    pass
                if last:
                    matches.append((len(v), last.start(), v, 0.95, "enum"))
            if matches:
                matches.sort(key=lambda x: (x[0], x[1]))
                _, _, value, conf, source = matches[-1]
                return {
                    "field": field_id,
                    "value": value,
                    "confidence": conf,
                    "needs_clarification": False,
                    "source": source,
                }
            return self._miss(field_id)

        if vtype == "integer":
            nums = re.findall(r"\b(\d{1,2})\b", raw)
            word_map = {
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
                "eight": 8,
                "nine": 9,
                "ten": 10,
            }
            for w, n in word_map.items():
                if re.search(rf"\b{w}\b", lowered):
                    nums.append(str(n))
            if nums:
                n = int(nums[0])
                mn = validation.get("min", 0)
                mx = validation.get("max", 100)
                if mn <= n <= mx:
                    return {
                        "field": field_id,
                        "value": n,
                        "confidence": 0.92,
                        "needs_clarification": False,
                        "source": "integer",
                    }
            return self._miss(field_id)

        # text
        cleaned = re.sub(r"[^\w\s&\-]", "", raw).strip()
        if len(cleaned) >= validation.get("min_length", 1):
            # strip filler
            cleaned = re.sub(
                r"^(it'?s|its|my|currently|we use|we have|um+|uh+)\s+",
                "",
                cleaned,
                flags=re.I,
            ).strip()
            if cleaned:
                return {
                    "field": field_id,
                    "value": self._canonical_text(cleaned, step),
                    "confidence": 0.85,
                    "needs_clarification": len(cleaned) < 3,
                    "source": "text",
                }
        return self._miss(field_id)

    @staticmethod
    def _canonical_text(cleaned: str, step: dict[str, Any]) -> str:
        """Tidy free text without mangling it.

        Blind title-casing turned "AGL" into "Agl", which then went into the
        payload. Known suppliers are snapped to the spelling the journey
        definition uses, and acronyms are left alone.
        """
        for example in step.get("examples", []) or []:
            if cleaned.lower() == str(example).lower():
                return str(example)
        if cleaned.isupper():
            return cleaned
        if step["id"] == "current_supplier":
            return " ".join(
                w if w.isupper() else w.capitalize() for w in cleaned.split()
            )
        return cleaned

    def _normalize(self, value: Any, validation: dict) -> Any:
        vtype = validation.get("type")
        if vtype == "enum":
            aliases = validation.get("aliases", {})
            values = validation.get("values", [])
            s = str(value).lower().strip()
            if s in aliases:
                return aliases[s]
            if s in values:
                return s
            for v in values:
                if v in s:
                    return v
            return None
        if vtype == "integer":
            try:
                n = int(value)
            except Exception:
                return None
            if validation.get("min", 0) <= n <= validation.get("max", 100):
                return n
            return None
        if vtype == "regex":
            s = str(value).strip()
            if re.fullmatch(validation.get("pattern", ".*"), s):
                return s
            return None
        return value

    @staticmethod
    def _miss(field_id: str) -> dict[str, Any]:
        return {
            "field": field_id,
            "value": None,
            "confidence": 0.2,
            "needs_clarification": True,
            "source": "none",
        }
