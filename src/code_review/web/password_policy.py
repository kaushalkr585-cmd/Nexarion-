from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from zxcvbn import zxcvbn

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

STRENGTH_LABELS: dict[int, str] = {
    0: "Very Weak",
    1: "Weak",
    2: "Medium",
    3: "Strong",
    4: "Very Strong",
}

_COMMON_CORES = {
    "password",
    "passw0rd",
    "qwerty",
    "asdfgh",
    "zxcvbn",
    "letmein",
    "welcome",
    "admin",
    "administrator",
    "iloveyou",
    "monkey",
    "dragon",
    "baseball",
    "football",
    "sunshine",
    "princess",
    "nexarion",
}

_KEYBOARD_ROWS = (
    "qwertyuiop",
    "poiuytrewq",
    "asdfghjkl",
    "lkjhgfdsa",
    "zxcvbnm",
    "mnbvcxz",
    "1234567890",
    "0987654321",
    "abcdefghijklmnopqrstuvwxyz",
    "zyxwvutsrqponmlkjihgfedcba",
)


@dataclass(frozen=True)
class PasswordEvaluation:
    score: int
    label: str
    acceptable: bool
    warning: str
    suggestions: list[str]
    crack_time_display: str
    checks: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "label": self.label,
            "acceptable": self.acceptable,
            "warning": self.warning,
            "suggestions": list(self.suggestions),
            "crack_time_display": self.crack_time_display,
            "checks": dict(self.checks),
        }


def _extract_user_tokens(name: str | None, email: str | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    def _add_candidate(raw: str | None) -> None:
        if not raw:
            return
        for part in re.split(r"[^a-zA-Z0-9]+", raw.lower()):
            if len(part) >= 3 and part not in seen:
                seen.add(part)
                tokens.append(part)

    _add_candidate(name)
    if email:
        _add_candidate(email.split("@")[0])
        if "@" in email:
            domain_head = email.split("@", 1)[1].split(".", 1)[0]
            _add_candidate(domain_head)
    return tokens


def _has_predictable_sequence(password: str) -> bool:
    lower = password.lower()
    if len(lower) < 5:
        return False

    for row in _KEYBOARD_ROWS:
        for i in range(len(row) - 4):
            seq = row[i : i + 5]
            if seq in lower:
                return True

    # Detect monotonic ascending/descending ASCII runs of length >= 5
    run_asc = 1
    run_desc = 1
    for idx in range(1, len(lower)):
        diff = ord(lower[idx]) - ord(lower[idx - 1])
        if diff == 1 and lower[idx].isalnum():
            run_asc += 1
        else:
            run_asc = 1
        if diff == -1 and lower[idx].isalnum():
            run_desc += 1
        else:
            run_desc = 1
        if run_asc >= 5 or run_desc >= 5:
            return True

    return False


def _has_repeated_pattern(password: str) -> bool:
    if not password:
        return False
    if re.search(r"(.)\1{3,}", password):
        return True
    if len(password) >= 8 and re.fullmatch(r"(.{1,4})\1+", password):
        return True
    return False


def evaluate_password_strength(
    password: str,
    *,
    name: str | None = None,
    email: str | None = None,
) -> PasswordEvaluation:
    """Evaluate password strength using zxcvbn entropy plus explicit policy checks.

    Never logs or persists the plaintext password. Prioritizes length and unpredictability
    over rigid uppercase/digit/symbol composition rules.
    """
    pwd = password or ""
    lower = pwd.lower()

    min_length_ok = len(pwd) >= MIN_PASSWORD_LENGTH
    max_length_ok = len(pwd) <= MAX_PASSWORD_LENGTH

    user_tokens = _extract_user_tokens(name, email)
    contains_personal_info = any(tok in lower for tok in user_tokens)
    has_repeated = _has_repeated_pattern(pwd)
    has_sequence = _has_predictable_sequence(pwd)

    user_inputs = ["nexarion", *user_tokens]
    analysis = zxcvbn(pwd[:MAX_PASSWORD_LENGTH], user_inputs=user_inputs) if pwd else None

    raw_score = int(analysis["score"]) if analysis else 0
    crack_time = (
        str(analysis.get("crack_times_display", {}).get("offline_slow_hashing_1e4_per_second", ""))
        if analysis
        else "instant"
    )
    feedback = analysis.get("feedback", {}) if analysis else {}
    raw_warning = str(feedback.get("warning") or "").strip()
    raw_suggestions = [str(s) for s in (feedback.get("suggestions") or []) if s]

    stripped_alpha = re.sub(r"[^a-z]", "", lower)
    is_common = (
        stripped_alpha in _COMMON_CORES
        or (raw_score <= 1 and "common" in raw_warning.lower())
        or (
            analysis is not None
            and any(
                m.get("pattern") == "dictionary"
                and (m.get("rank") or 999999) <= 2000
                and len(str(m.get("token") or "")) >= max(5, int(len(pwd) * 0.65))
                for m in (analysis.get("sequence") or [])
            )
        )
    )

    effective_score = raw_score
    if not min_length_ok:
        effective_score = min(effective_score, 1 if len(pwd) >= 8 else 0)
    if contains_personal_info or has_repeated or has_sequence or is_common:
        effective_score = min(effective_score, 2 if min_length_ok and raw_score >= 3 else 1)
    if not pwd or not max_length_ok:
        effective_score = 0

    suggestions: list[str] = []
    if not min_length_ok:
        suggestions.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if not max_length_ok:
        suggestions.append(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    if contains_personal_info:
        suggestions.append("Avoid including your name or email address inside your password.")
    if has_repeated:
        suggestions.append("Avoid repeated characters or repeating short patterns (e.g. aaaa).")
    if has_sequence:
        suggestions.append(
            "Avoid predictable sequences such as 123456, abcdef, or keyboard patterns like qwerty."
        )
    if is_common:
        suggestions.append("Avoid commonly used or compromised passwords.")
    for item in raw_suggestions:
        if item not in suggestions:
            suggestions.append(item)

    acceptable = (
        min_length_ok
        and max_length_ok
        and not contains_personal_info
        and not has_repeated
        and not has_sequence
        and not is_common
        and effective_score >= 3
    )

    if not acceptable and not suggestions:
        suggestions.append(
            "Your password is too weak. Try using a longer password with a combination of unpredictable words."
        )

    warning = raw_warning
    if not acceptable:
        if not min_length_ok:
            warning = f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        elif not max_length_ok:
            warning = f"Password must not exceed {MAX_PASSWORD_LENGTH} characters."
        elif contains_personal_info:
            warning = "Password cannot include parts of your name or email."
        elif is_common:
            warning = "This password is too common and easily guessed."
        elif has_sequence:
            warning = "Predictable character or keyboard sequences weaken this password."
        elif has_repeated:
            warning = "Repeated characters or patterns make this password easy to guess."
        elif not warning:
            warning = (
                "Your password is too weak. Try using a longer password with a combination "
                "of unpredictable words."
            )

    return PasswordEvaluation(
        score=effective_score,
        label=STRENGTH_LABELS.get(effective_score, "Very Weak"),
        acceptable=acceptable,
        warning=warning,
        suggestions=suggestions,
        crack_time_display=crack_time or "instant",
        checks={
            "min_length": min_length_ok,
            "max_length": max_length_ok,
            "not_common": not is_common,
            "no_predictable_sequence": not has_sequence,
            "no_repeated_pattern": not has_repeated,
            "no_personal_info": not contains_personal_info,
            "sufficient_entropy": effective_score >= 3,
        },
    )
