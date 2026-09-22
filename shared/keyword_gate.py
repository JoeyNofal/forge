"""
Word-boundary-safe keyword matching for agent refusal gates.

Old bug (Lesson #6): "code" in message.lower() matches "food",
"program" matches "workout program". This uses regex word
boundaries so only whole words match.
"""
import re

def contains_keyword(text: str, keywords: list[str]) -> bool:
    """
    Returns True if any keyword in `keywords` appears in `text` as a
    whole word (or exact phrase, for multi-word keywords like
    "stock market"). Case-insensitive.
    """
    text_lower = text.lower()
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text_lower):
            return True
    return False


def should_refuse(message: str, non_topic_keywords: list[str],
                   intent_override_keywords: list[str] = None) -> bool:
    """
    Standard refusal check used by every agent's keyword gate.

    message                   — the user's message
    non_topic_keywords        — words that suggest a DIFFERENT agent's
                                 topic (e.g. CIPHER's NON_CODING list)
    intent_override_keywords  — words that, if present, mean "actually
                                 this IS my topic" and should cancel
                                 the refusal (e.g. CIPHER's
                                 CODING_INTENT list). Optional.

    Returns True if the agent should refuse.
    """
    looks_off_topic = contains_keyword(message, non_topic_keywords)
    if not looks_off_topic:
        return False

    if intent_override_keywords and contains_keyword(message, intent_override_keywords):
        return False

    return True