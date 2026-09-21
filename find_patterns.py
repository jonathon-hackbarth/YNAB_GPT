"""Scans transaction history for merchants with high, consistent category agreement
that aren't already covered by overrides.py, and surfaces them as candidate rules to
add. Turns "notice a mistake, manually dig through months of data" (what we did by
hand to find the AplPay patterns) into a repeatable, few-minute periodic review.

Doesn't touch YNAB or write anything -- read-only, prints candidates for you to
review and add to overrides.py yourself.

Two filters run before anything is called a "candidate":
  - Time spread: occurrences must span multiple distinct calendar months. A merchant that
    shows up 3 times in one week is one real-world event (a trip, a shopping spree), not a
    recurring pattern -- hardcoding a rule from it is actively wrong for the next occurrence.
  - Plausibility: Claude sanity-checks each surviving merchant/category pairing against
    real-world sense, to catch cases where the data is just consistently wrong (e.g. a
    password manager subscription that got miscategorized as a gift the same way every time).
    Consistency in the data proves the pattern happened; it doesn't prove it was ever correct.

Usage:
    python3 find_patterns.py                          # scan the live budget, last 180 days
    python3 find_patterns.py --days 365                # wider window
    python3 find_patterns.py --min-count 5              # require more occurrences
    python3 find_patterns.py --min-months 3             # require a wider time spread
    python3 find_patterns.py --skip-plausibility        # skip the Claude sanity-check pass
    python3 find_patterns.py --budget-id <id>           # scan a different budget (e.g. the archived one)
"""
import argparse
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

import requests

if 'YNAB_API_KEY' not in os.environ:
    env = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k] = v
    os.environ.setdefault('YNAB_API_KEY', env['YNAB_API_KEY'])
    os.environ.setdefault('ANTHROPIC_API_KEY', env.get('ANTHROPIC_API_KEY', ''))

import gpt
import overrides
import ynab

NOISE_PATTERNS = [
    re.compile(r'^\d{4}-\d{2}-\d{2}:\s*'),  # leading date
    re.compile(r'\s+in\s+[A-Z ]+,\s*[A-Z]{2}$', re.IGNORECASE),  # trailing "in CITY, ST"
    re.compile(r'#\s*-?\d+'),  # store numbers
    re.compile(r'\*[A-Z0-9]+'),  # processor suffix codes like *5Q3GC9WD0
    re.compile(r'\d{3,}'),  # long digit runs (order ids, phone numbers)
]


def clean_for_grouping(payee: str) -> str:
    text = overrides.normalize_payee(payee)
    for pattern in NOISE_PATTERNS:
        text = pattern.sub('', text)
    return re.sub(r'\s+', ' ', text).strip().upper()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--days', type=int, default=180, help='How many days of history to scan (default 180)')
    parser.add_argument('--min-count', type=int, default=3, help='Minimum occurrences to consider a candidate (default 3)')
    parser.add_argument('--min-consistency', type=float, default=0.9, help='Minimum share going to the dominant category (default 0.9)')
    parser.add_argument('--min-months', type=int, default=2, help='Minimum distinct calendar months the occurrences must span (default 2)')
    parser.add_argument('--skip-plausibility', action='store_true', help="Skip Claude's sanity-check pass on surviving candidates")
    parser.add_argument('--budget-id', default=None, help='Budget to scan (default: the live budget from ynab.py)')
    args = parser.parse_args()

    budget_id = args.budget_id or ynab.BUDGET_ID
    resp = requests.get(f'https://api.ynab.com/v1/budgets/{budget_id}/transactions', headers=ynab.DEFAULT_HEADERS)
    resp.raise_for_status()
    transactions = resp.json()['data']['transactions']

    cat_resp = requests.get(f'https://api.ynab.com/v1/budgets/{budget_id}/categories', headers=ynab.DEFAULT_HEADERS)
    cat_resp.raise_for_status()
    category_name = {}
    for cg in cat_resp.json()['data']['category_groups']:
        for c in cg['categories']:
            category_name[c['id']] = f"{cg['name']}/{c['name']}"

    cutoff = (date.today() - timedelta(days=args.days)).isoformat()
    real = [
        t for t in transactions
        if not t.get('deleted') and not t.get('transfer_account_id')
        and t.get('amount', 0) < 0 and t.get('date', '') >= cutoff
        and t.get('import_payee_name_original')
    ]

    by_merchant = defaultdict(list)
    already_covered = 0
    for t in real:
        payee = t['import_payee_name_original']
        if overrides.lookup_category(payee) is not None:
            already_covered += 1
            continue
        by_merchant[clean_for_grouping(payee)].append(t)

    candidates = []
    thin_spread = 0
    for merchant, txns in by_merchant.items():
        if len(txns) < args.min_count:
            continue
        cat_counts = Counter(category_name.get(t.get('category_id'), '(uncategorized)') for t in txns)
        top_category, top_count = cat_counts.most_common(1)[0]
        consistency = top_count / len(txns)
        if top_category == '(uncategorized)' or consistency < args.min_consistency:
            continue
        distinct_months = len({t['date'][:7] for t in txns})
        if distinct_months < args.min_months:
            thin_spread += 1
            continue
        candidates.append((merchant, len(txns), top_category, consistency, distinct_months, txns[0]['import_payee_name_original']))
    candidates.sort(key=lambda c: -c[1])

    print(f'Scanned {len(real)} spending transactions from the last {args.days} days ({already_covered} already covered by an existing rule).')
    print(f'{thin_spread} merchant(s) hit the count/consistency bar but were clustered in too few months -- filtered as likely one-time events, not patterns.')
    print(f'Found {len(candidates)} candidate merchant(s) after the time-spread filter:\n')
    if not candidates:
        print('(none -- either no new patterns yet, or everything consistent enough is already in overrides.py)')
        return

    if args.skip_plausibility:
        checked = [(m, c, cat, cons, mo, s, True, '') for m, c, cat, cons, mo, s in candidates]
    else:
        checked = []
        for merchant, count, top_category, consistency, distinct_months, sample in candidates:
            is_plausible, reason = gpt.sanity_check(sample, top_category)
            checked.append((merchant, count, top_category, consistency, distinct_months, sample, is_plausible, reason))

    plausible = [c for c in checked if c[6]]
    questionable = [c for c in checked if not c[6]]

    def print_row(merchant, count, top_category, consistency, distinct_months, sample):
        print(f'{merchant[:34]:35} {count:>6}  {distinct_months:>6} months  {consistency:>9.0%}  {top_category}')
        print(f'    sample raw payee: {sample!r}')

    print(f"\n{'MERCHANT':35} {'COUNT':>6}  {'SPREAD':>10}  {'CONSISTENCY':>9}  DOMINANT CATEGORY")
    print('=== Recommended ===')
    for merchant, count, top_category, consistency, distinct_months, sample, _, _ in plausible:
        print_row(merchant, count, top_category, consistency, distinct_months, sample)

    if questionable:
        print('\n=== Questionable -- consistent in the data, but Claude flagged the pairing itself as suspect ===')
        for merchant, count, top_category, consistency, distinct_months, sample, _, reason in questionable:
            print_row(merchant, count, top_category, consistency, distinct_months, sample)
            print(f'    why: {reason}')

    print()
    print("To add one, append to MERCHANT_RULES in overrides.py:")
    print("    (re.compile(r'YOUR_PATTERN', re.IGNORECASE), 'category name here'),")
    if not args.skip_plausibility:
        print(f'\nClaude tokens used - input: {gpt.usage_prompt_tokens}, output: {gpt.usage_completion_tokens}')


if __name__ == '__main__':
    main()
