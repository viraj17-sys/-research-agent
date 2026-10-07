"""
Content safety filter for Research Agent.

This filter applies to ALL users, regardless of age.
It blocks requests for explicit, harmful, or dangerous content.
"""

import re


# ---------------------------------------------------------
# BLOCKED CONTENT PATTERNS
# ---------------------------------------------------------

BLOCKED_PATTERNS = [
    # Explicit sexual / pornographic content
    r"\bporn\b",
    r"\bpornography\b",
    r"\bxxx\b",
    r"\berotic\b",
    r"\berotica\b",
    r"\bsex\s*video\b",
    r"\bsex\s*videos\b",
    r"\bsexual\s*roleplay\b",
    r"\berotic\s*roleplay\b",
    r"\bnude\s*photos?\b",
    r"\bnude\s*images?\b",
    r"\bnaked\s*photos?\b",
    r"\bnaked\s*images?\b",
    r"\bexplicit\s*photos?\b",
    r"\bexplicit\s*images?\b",
    r"\bsexual\s*images?\b",
    r"\bsexual\s*content\b",
    r"\bsexually\s*explicit\b",

    # Common explicit requests
    r"\bblowjob\b",
    r"\boral\s*sex\b",
    r"\banal\s*sex\b",
    r"\bsex\s*positions?\b",
    r"\bsex\s*scenes?\b",
    r"\berotic\s*stories?\b",
    r"\berotic\s*story\b",
    r"\bsexual\s*fantasy\b",
    r"\bsexual\s*fantasies\b",
    r"\bsexting\b",
    r"\bsexy\s*chat\b",

    # Sexual services / explicit generation
    r"\bgenerate\s+porn\b",
    r"\bcreate\s+porn\b",
    r"\bwrite\s+porn\b",
    r"\bwrite\s+an\s+erotic\b",
    r"\bcreate\s+an\s+erotic\b",

    # Self-harm / suicide instructions
    r"\bhow\s+to\s+kill\s+myself\b",
    r"\bhow\s+to\s+commit\s+suicide\b",
    r"\bsuicide\s+method\b",
    r"\bsuicide\s+methods\b",
    r"\bways\s+to\s+kill\s+myself\b",
    r"\bways\s+to\s+commit\s+suicide\b",
    r"\bhow\s+to\s+self[-\s]?harm\b",

    # Dangerous/violent instructions
    r"\bhow\s+to\s+make\s+a\s+bomb\b",
    r"\bhow\s+to\s+build\s+a\s+bomb\b",
    r"\bhow\s+to\s+make\s+an\s+explosive\b",
    r"\bhow\s+to\s+build\s+an\s+explosive\b",
]


# ---------------------------------------------------------
# CHECK CONTENT
# ---------------------------------------------------------

def is_restricted_content(text: str) -> bool:
    """
    Return True when text contains a restricted-content pattern.
    """

    if not text:
        return False

    normalized = re.sub(r"\s+", " ", text.lower()).strip()

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return True

    return False


# ---------------------------------------------------------
# USER-FACING MESSAGE
# ---------------------------------------------------------

RESTRICTION_MESSAGE = (
    "🛡️ **Content Restricted**\n\n"
    "I can't help generate explicit, harmful, or dangerous content.\n\n"
    "I can help with safe, educational, scientific, "
    "or research-related information instead."
)