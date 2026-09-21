"""Deterministic payee -> category rules, checked before ever calling Claude.

PREFIX_PATTERNS strip known payment-processor noise (e.g. "AplPay 365 VEND" -> "365 VEND")
so both this lookup and Claude see the real merchant, not the processor. Applied once via
normalize_payee() and reused by gpt.categorize() too.

MERCHANT_RULES matches the *normalized* payee against merchants with near-100% historical
consistency (see analyze_categories.py / historical_usage.py for the analysis behind each
entry). Category names are the bare lowercase name YNAB uses (matching
Category.get_name().lower()), not "group/name".

Do NOT add a merchant whose purchases genuinely vary in kind -- Amazon, Venmo, PayPal, and
Kwik Trip were all checked against months of history and confirmed non-deterministic (same
merchant, many different real categories). A wrong hardcoded rule is worse than no rule;
those need Claude's per-transaction judgment.
"""
import re

PREFIX_PATTERNS = [
    re.compile(r'^AplPay\s+', re.IGNORECASE),
    re.compile(r'^DD\s*\*\s*', re.IGNORECASE),
    re.compile(r'^TST\*\s*', re.IGNORECASE),
    re.compile(r'^SQ\s*\*\s*', re.IGNORECASE),
    re.compile(r'^SP\s+', re.IGNORECASE),
]

MERCHANT_RULES = [
    (re.compile(r'365 VEND', re.IGNORECASE), 'food out'),
    (re.compile(r'DOORDASH', re.IGNORECASE), 'food out'),
    (re.compile(r'PICK N SAVE', re.IGNORECASE), 'groceries'),
    (re.compile(r'FESTIVAL FOOD', re.IGNORECASE), 'groceries'),
    (re.compile(r'^BP#', re.IGNORECASE), 'gas'),
]


def normalize_payee(payee: str) -> str:
    for pattern in PREFIX_PATTERNS:
        payee = pattern.sub('', payee)
    return payee.strip()


def lookup_category(payee: str) -> str | None:
    """Returns the lowercase category name for a deterministic merchant match, or None."""
    normalized = normalize_payee(payee)
    for pattern, category_name in MERCHANT_RULES:
        if pattern.search(normalized):
            return category_name
    return None


def validate_rules(category_map: dict) -> list[str]:
    """Returns a warning per rule whose target category no longer exists in the live budget
    (e.g. after a category rename), so stale rules are caught loudly instead of silently
    failing to match.
    """
    return [
        f'Override rule for {pattern.pattern!r} points to missing category {category_name!r}'
        for pattern, category_name in MERCHANT_RULES
        if category_name not in category_map
    ]
