import os
import sys

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
import main as ynab_main

SAMPLE_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 200

transactions, server_knowledge = ynab.get_transactions()
categories = ynab.get_categories()
category_by_id = {c.category_id: c for c in categories}
transfers = [t for t in transactions if t.transfer_account_id]
non_transfers = [t for t in transactions if not t.transfer_account_id]
sample = non_transfers[:SAMPLE_SIZE]

print(f'{len(transfers)} of {len(transactions)} unapproved transactions are transfers (skipped, no Claude call).')
print(f'{len(non_transfers)} are real (non-transfer) transactions Claude will look at.')
print(f'Sampling {len(sample)} of those — NOT writing anything to YNAB.\n')

results = ynab_main.categorize_transactions(sample, categories)

print()
new_count = corrected_count = confirmed_count = unmatched_count = 0
for t in sample:
    payee = t.import_payee_name_original or '(no payee name)'
    existing = category_by_id.get(t.category_id)
    existing_name = existing.full_name() if existing else None

    if t.id in results:
        new_cat = results[t.id]
        if existing_name is None:
            print(f'{payee!r:50} NEW           -> {new_cat.full_name()}')
            new_count += 1
        else:
            print(f'{payee!r:50} CORRECTED     {existing_name!r} -> {new_cat.full_name()!r}')
            corrected_count += 1
    elif existing_name is not None:
        confirmed_count += 1
    else:
        unmatched_count += 1

print()
print(f'Sample size: {len(sample)}')
print(f'Would newly categorize (was blank): {new_count}')
print(f'Would correct (Claude disagreed with existing category): {corrected_count}')
print(f'Confirmed / left unchanged (already categorized, Claude agrees): {confirmed_count}')
print(f'Left as "other" / no match: {unmatched_count}')
print(f'Claude tokens used - input: {gpt.usage_prompt_tokens}, output: {gpt.usage_completion_tokens}')
