from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SelectorCandidate:
    strategy: str
    locator: str
    confidence: float = 1.0


def build_text_locators(option_text: str) -> List[SelectorCandidate]:
    safe_text = option_text.strip()
    return [
        SelectorCandidate("text", f"text={safe_text}", 0.9),
        SelectorCandidate("aria", f"aria/{safe_text}", 0.8),
        SelectorCandidate("xpath", f"//button[contains(., '{safe_text}')]|//label[contains(., '{safe_text}')]", 0.7),
    ]


def select_best(candidates: List[SelectorCandidate]) -> Optional[SelectorCandidate]:
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: c.confidence, reverse=True)[0]
