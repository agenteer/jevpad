from __future__ import annotations

from copy import deepcopy


MODES = ("live", "fixture")


def mode_label(mode: str, injected_fault: str | None = None) -> str:
    """Label for one result row or evidence record: LIVE, FIXTURE, or INJECTED FAULT (KIND)."""
    if mode == "live" and injected_fault:
        return f"INJECTED FAULT ({injected_fault.upper()})"
    return mode.upper()


def banner(mode: str, *, original_timestamp: str | None = None, injected_fault: str | None = None) -> str:
    if mode == "live" and injected_fault:
        return f"=== INJECTED FAULT ({injected_fault.upper()}) · NO PROVIDER CALL ==="
    if mode == "live":
        return "=== LIVE · FRESH MODEL OUTPUT ==="
    if mode == "fixture":
        return "=== FIXTURE · NOT MODEL OUTPUT ==="
    if mode == "replay":
        suffix = f" · ORIGINAL UTC {original_timestamp}" if original_timestamp else ""
        if injected_fault:
            return f"=== REPLAY · RECORDED INJECTED FAULT ({injected_fault.upper()}) · NO PROVIDER CALL{suffix} ==="
        return f"=== REPLAY · RECORDED LIVE OUTPUT{suffix} ==="
    if mode == "evidence":
        return "=== SAVED EVIDENCE · NO PROVIDER CALL ==="
    raise ValueError(f"Unknown mode: {mode}")


MESSAGE_FIXTURES = {
    "M01": ("billing", 0.91, 0.98, 0.90, 1.35, 0.68),
    "M02": ("billing", 0.88, 0.04, 0.54, 0.55, 0.77),
    "M03": ("technical_support", 0.95, 0.01, 0.97, 1.88, 0.91),
    "M04": ("sales", 0.93, 0.01, 0.94, 0.62, 0.79),
    "M05": ("sales", 0.94, 0.01, 0.91, 0.71, 0.84),
    "M06": ("technical_support", 0.91, 0.01, 0.73, 1.14, 0.66),
    "M07": ("other", 0.82, 0.01, 0.06, 0.12, 0.90),
    "M08": ("other", 0.31, 0.01, 0.90, 0.86, 0.25),
    "M09": ("billing", 0.68, 0.01, 0.89, 1.02, 0.48),
    "M10": ("sales", 0.55, 0.01, 0.95, 0.91, 0.32),
}

# Hand-written offline answers for data/academy-articles.csv × data/readers.csv, labeled FIXTURE · NOT MODEL OUTPUT.
# Only the readers shipped in data/readers.csv have fixtures; a reader you add runs live.
# Per article: (relevance score 0-3, confidence, opinion_or_overview P(yes)).
READING_FIXTURES = {
    "dental_office": {
        "how-ai-agents-actually-work": (0.72, 0.68, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (2.78, 0.76, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (2.93, 0.79, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.05, 0.62, 0.95),
        "intent-is-all-you-need-still": (0.64, 0.69, 0.88),
        "loop-engineering": (0.88, 0.65, 0.80),
        "hermes-agent-oracle-cloud": (0.12, 0.78, 0.04),
        "hermes-agent-ai-customer-support-team": (1.22, 0.60, 0.08),
        "grok-bot-ai-customer-support-team": (0.95, 0.64, 0.10),
        "mac-setup-agentic-engineering": (0.05, 0.79, 0.03),
        "hyperframes-from-zero": (0.48, 0.72, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.08, 0.79, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.06, 0.79, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (0.71, 0.68, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.33, 0.74, 0.92),
    },
    "restaurant": {
        "how-ai-agents-actually-work": (0.61, 0.70, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (2.71, 0.75, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (2.88, 0.78, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.12, 0.61, 0.95),
        "intent-is-all-you-need-still": (0.55, 0.71, 0.88),
        "loop-engineering": (0.79, 0.67, 0.80),
        "hermes-agent-oracle-cloud": (0.10, 0.78, 0.04),
        "hermes-agent-ai-customer-support-team": (1.35, 0.58, 0.08),
        "grok-bot-ai-customer-support-team": (1.02, 0.63, 0.10),
        "mac-setup-agentic-engineering": (0.04, 0.79, 0.03),
        "hyperframes-from-zero": (1.58, 0.56, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.07, 0.79, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.05, 0.79, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (0.58, 0.70, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.41, 0.73, 0.92),
    },
    "accounting_firm": {
        "how-ai-agents-actually-work": (1.12, 0.61, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (2.46, 0.71, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (1.31, 0.58, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.38, 0.57, 0.95),
        "intent-is-all-you-need-still": (1.05, 0.62, 0.88),
        "loop-engineering": (1.92, 0.62, 0.80),
        "hermes-agent-oracle-cloud": (0.18, 0.77, 0.04),
        "hermes-agent-ai-customer-support-team": (1.74, 0.59, 0.08),
        "grok-bot-ai-customer-support-team": (1.41, 0.57, 0.10),
        "mac-setup-agentic-engineering": (0.06, 0.79, 0.03),
        "hyperframes-from-zero": (0.21, 0.77, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.12, 0.78, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.15, 0.78, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (2.36, 0.69, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.62, 0.70, 0.92),
    },
    "real_estate_agent": {
        "how-ai-agents-actually-work": (0.66, 0.69, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (2.58, 0.73, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (2.62, 0.74, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (0.98, 0.64, 0.95),
        "intent-is-all-you-need-still": (0.52, 0.71, 0.88),
        "loop-engineering": (0.94, 0.64, 0.80),
        "hermes-agent-oracle-cloud": (0.14, 0.78, 0.04),
        "hermes-agent-ai-customer-support-team": (1.28, 0.59, 0.08),
        "grok-bot-ai-customer-support-team": (1.06, 0.62, 0.10),
        "mac-setup-agentic-engineering": (0.04, 0.79, 0.03),
        "hyperframes-from-zero": (1.21, 0.60, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.06, 0.79, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.05, 0.79, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (0.49, 0.72, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.37, 0.74, 0.92),
    },
    "marketing_agency": {
        "how-ai-agents-actually-work": (1.21, 0.60, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (2.12, 0.65, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (0.74, 0.68, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.66, 0.58, 0.95),
        "intent-is-all-you-need-still": (1.83, 0.61, 0.88),
        "loop-engineering": (2.47, 0.71, 0.80),
        "hermes-agent-oracle-cloud": (0.16, 0.77, 0.04),
        "hermes-agent-ai-customer-support-team": (0.92, 0.65, 0.08),
        "grok-bot-ai-customer-support-team": (0.88, 0.65, 0.10),
        "mac-setup-agentic-engineering": (0.09, 0.79, 0.03),
        "hyperframes-from-zero": (2.52, 0.72, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.34, 0.74, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.22, 0.76, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (1.18, 0.60, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.44, 0.73, 0.92),
    },
    "ecommerce_shop": {
        "how-ai-agents-actually-work": (0.94, 0.64, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (2.35, 0.69, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (1.12, 0.61, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.08, 0.62, 0.95),
        "intent-is-all-you-need-still": (0.61, 0.70, 0.88),
        "loop-engineering": (1.47, 0.56, 0.80),
        "hermes-agent-oracle-cloud": (0.31, 0.75, 0.04),
        "hermes-agent-ai-customer-support-team": (2.41, 0.70, 0.08),
        "grok-bot-ai-customer-support-team": (2.18, 0.66, 0.10),
        "mac-setup-agentic-engineering": (0.05, 0.79, 0.03),
        "hyperframes-from-zero": (0.86, 0.66, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.09, 0.79, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.08, 0.79, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (0.92, 0.65, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (1.36, 0.57, 0.92),
    },
    "ops_lead": {
        "how-ai-agents-actually-work": (1.84, 0.61, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (1.23, 0.60, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (0.58, 0.70, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.15, 0.61, 0.95),
        "intent-is-all-you-need-still": (1.78, 0.60, 0.88),
        "loop-engineering": (2.41, 0.70, 0.80),
        "hermes-agent-oracle-cloud": (0.34, 0.74, 0.04),
        "hermes-agent-ai-customer-support-team": (1.92, 0.62, 0.08),
        "grok-bot-ai-customer-support-team": (1.81, 0.60, 0.10),
        "mac-setup-agentic-engineering": (0.11, 0.78, 0.03),
        "hyperframes-from-zero": (0.07, 0.79, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (0.62, 0.70, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (0.45, 0.73, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (2.95, 0.79, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (2.12, 0.65, 0.92),
    },
    "support_developer": {
        "how-ai-agents-actually-work": (2.18, 0.66, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (0.41, 0.73, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (0.86, 0.66, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (0.18, 0.77, 0.95),
        "intent-is-all-you-need-still": (1.12, 0.61, 0.88),
        "loop-engineering": (1.88, 0.61, 0.80),
        "hermes-agent-oracle-cloud": (2.05, 0.64, 0.04),
        "hermes-agent-ai-customer-support-team": (2.94, 0.79, 0.08),
        "grok-bot-ai-customer-support-team": (2.89, 0.78, 0.10),
        "mac-setup-agentic-engineering": (1.36, 0.57, 0.03),
        "hyperframes-from-zero": (0.52, 0.71, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (1.74, 0.59, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (2.31, 0.69, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (1.69, 0.58, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.62, 0.70, 0.92),
    },
    "solo_builder": {
        "how-ai-agents-actually-work": (2.21, 0.67, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (0.22, 0.76, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (0.35, 0.74, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (0.31, 0.75, 0.95),
        "intent-is-all-you-need-still": (1.02, 0.63, 0.88),
        "loop-engineering": (1.84, 0.61, 0.80),
        "hermes-agent-oracle-cloud": (2.91, 0.79, 0.04),
        "hermes-agent-ai-customer-support-team": (1.96, 0.63, 0.08),
        "grok-bot-ai-customer-support-team": (1.72, 0.59, 0.10),
        "mac-setup-agentic-engineering": (2.58, 0.73, 0.03),
        "hyperframes-from-zero": (1.12, 0.61, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (2.24, 0.67, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (2.37, 0.70, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (1.61, 0.57, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (0.84, 0.66, 0.92),
    },
    "student": {
        "how-ai-agents-actually-work": (2.88, 0.78, 0.30),
        "ai-for-your-small-business-what-it-can-do-in-your-industry-and-how-to-start": (0.95, 0.64, 0.62),
        "why-voice-ai-agents-are-no-longer-optional-a-practical-guide-for-small-business-owners": (0.72, 0.68, 0.55),
        "exploring-ai-native-vs-ai-augmented-business-models-in-the-genai-era": (1.24, 0.59, 0.95),
        "intent-is-all-you-need-still": (1.71, 0.59, 0.88),
        "loop-engineering": (2.14, 0.66, 0.80),
        "hermes-agent-oracle-cloud": (1.42, 0.56, 0.04),
        "hermes-agent-ai-customer-support-team": (1.53, 0.56, 0.08),
        "grok-bot-ai-customer-support-team": (1.38, 0.57, 0.10),
        "mac-setup-agentic-engineering": (1.12, 0.61, 0.03),
        "hyperframes-from-zero": (0.96, 0.64, 0.05),
        "unlock-claude-codes-power-through-the-capability-lifecycle": (1.61, 0.57, 0.52),
        "the-two-context-bloat-problems-every-ai-agent-builder-must-understand": (1.97, 0.63, 0.45),
        "security-analysis-of-openclaw-and-the-ai-agent-era": (1.83, 0.61, 0.90),
        "what-an-ai-agent-can-pay-with-in-2026": (1.05, 0.62, 0.92),
    },
}

def fixture_answers(recipe: str, example_id: str, profile: str | None = None) -> dict:
    if recipe == "messages":
        team, team_conf, refund, reply, urgency, urgency_conf = MESSAGE_FIXTURES.get(
            example_id, ("other", 0.25, 0.1, 0.7, 0.8, 0.3)
        )
        return {
            "team": {"type": "choice", "choice": team, "confidence": team_conf,
                     "probabilities": {team: team_conf}},
            "requests_refund": {"type": "noul", "noul": refund},
            "expects_reply": {"type": "noul", "noul": reply},
            "urgency": {"type": "score", "score": urgency, "confidence": urgency_conf,
                        "probabilities": {str(round(urgency)): urgency_conf}},
        }
    if recipe == "reading":
        score, confidence, overview = READING_FIXTURES.get(profile or "", {}).get(
            example_id, (1.0, 0.4, 0.2)
        )
        return {
            "relevance": {"type": "score", "score": score, "confidence": confidence,
                          "probabilities": {str(round(score)): confidence}},
            "opinion_or_overview": {"type": "noul", "noul": overview},
        }
    raise ValueError(f"No fixtures for recipe {recipe}")
