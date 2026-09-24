import os
import sys
from contextlib import closing

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v
os.environ.setdefault('YNAB_API_KEY', env['YNAB_API_KEY'])
os.environ.setdefault('ANTHROPIC_API_KEY', env['ANTHROPIC_API_KEY'])

import ynab
import gpt
import db
import main as ynab_main

SAMPLE_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 200
DB_PATH = './db.sqlite'

transactions, server_knowledge = ynab.get_transactions()
categories = ynab.get_categories()
category_by_id = {c.category_id: c for c in categories}
credit_card_accounts = [a for a in ynab.get_accounts() if a['type'] == 'creditCard']
ready_to_assign = ynab.get_ready_to_assign_category()
transfers = [t for t in transactions if t.transfer_account_id]
non_transfers = [t for t in transactions if not t.transfer_account_id]
sample = non_transfers[:SAMPLE_SIZE]

results, card_attention = ynab_main.categorize_transactions(sample, categories, credit_card_accounts)
income_matches = ynab_main.categorize_income(sample, ready_to_assign)
results.update(income_matches)
remaining_sample = [t for t in sample if t.id not in income_matches]
refund_matches, refund_attention = ynab_main.match_refund_categories(remaining_sample, ynab.get_all_transactions(), categories)
results.update(refund_matches)
attention_items = card_attention + refund_attention

# Attention items (things the tool looked at but couldn't resolve) are local bookkeeping only --
# nothing is written to YNAB either way, so it's safe to persist them even in a dry run. The
# regular `results` matches are NOT persisted here since nothing's actually been applied yet;
# that only happens for real in main.py.
with closing(db.RunStore(DB_PATH)) as store:
    unapproved_ids = {t.id for t in transactions}
    existing_touched = store.get_touched()
    current_attention_ids = {item.transaction_id for item in attention_items}
    resolved_attention_ids = [
        tid for tid, info in existing_touched.items()
        if info.category_name is None and tid in unapproved_ids and tid not in current_attention_ids
    ]
    stale_ids = [tid for tid in existing_touched if tid not in unapproved_ids]
    if resolved_attention_ids or stale_ids:
        store.forget_touched(resolved_attention_ids + stale_ids)
    if attention_items:
        store.record_touched(attention_items)
    touched = store.get_touched()
    still_pending = {tid: info for tid, info in touched.items() if tid in unapproved_ids}

transactions_by_id = {t.id: t for t in transactions}
print(f'{len(still_pending)} transaction(s) this tool has touched that you have NOT yet resolved in YNAB:')
if not still_pending:
    print('  (none)')
for tid, info in sorted(still_pending.items(), key=lambda kv: kv[1].dttm):
    t = transactions_by_id[tid]
    amount = t.amount / 1000
    if info.category_name is None:
        print(f'  {t.date}  ${amount:>8.2f}  {info.payee!r:50} NEEDS ATTENTION [{info.source}] {info.note}')
    else:
        cat = category_by_id.get(t.category_id)
        cat_name = cat.full_name() if cat else info.category_name
        tag = 'CORRECTED' if info.is_override else 'NEW'
        print(f'  {t.date}  ${amount:>8.2f}  {info.payee!r:50} {tag:>9} [{info.source}] -> {cat_name}')
print()

print(f'{len(transfers)} of {len(transactions)} unapproved transactions are transfers (skipped, no Claude call).')
print(f'{len(non_transfers)} are real (non-transfer) transactions Claude will look at.')
print(f'Sampling {len(sample)} of those — NOT writing anything to YNAB.\n')

print()
new_count = corrected_count = confirmed_count = unmatched_count = 0
for t in sample:
    payee = t.import_payee_name_original or '(no payee name)'
    existing = category_by_id.get(t.category_id)
    existing_name = existing.full_name() if existing else None

    if t.id in results:
        new_cat, is_override, source = results[t.id]
        tag = f'[{source}]'
        amount = t.amount / 1000
        if not is_override:
            print(f'{t.date}  ${amount:>8.2f}  {payee!r:50} NEW {tag:>8} -> {new_cat.full_name()}')
            new_count += 1
        else:
            print(f'{t.date}  ${amount:>8.2f}  {payee!r:50} CORRECTED {tag:>8} {existing_name!r} -> {new_cat.full_name()!r}')
            corrected_count += 1
    elif existing_name is not None:
        confirmed_count += 1
    else:
        unmatched_count += 1

print()
print(f'Sample size: {len(sample)}')
print(f'Would newly categorize (was blank): {new_count}')
print(f'Would correct (agreed twice, or a deterministic rule, disagreeing with existing category): {corrected_count}')
print(f'Confirmed / left unchanged (already categorized, Claude agrees): {confirmed_count}')
print(f'Left as "other" / no match: {unmatched_count}')
print(f'Claude tokens used - input: {gpt.usage_prompt_tokens}, output: {gpt.usage_completion_tokens}')
