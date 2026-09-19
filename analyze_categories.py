import re
import requests
from collections import Counter

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v

BUDGET_ID = 'last-used'
headers = {'accept': 'application/json', 'Authorization': f'Bearer {env["YNAB_API_KEY"]}'}

# All categories, including internal ones, for full usage picture
cat_resp = requests.get(f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/categories', headers=headers)
cat_resp.raise_for_status()
category_name = {}
for cg in cat_resp.json()['data']['category_groups']:
    for c in cg['categories']:
        category_name[c['id']] = f"{cg['name']}/{c['name']}"

tx_resp = requests.get(f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/transactions', headers=headers)
tx_resp.raise_for_status()
all_tx = tx_resp.json()['data']['transactions']

real = [t for t in all_tx if not t.get('deleted') and not t.get('transfer_account_id')]
print(f'Total transactions: {len(all_tx)}')
print(f'Non-transfer, non-deleted: {len(real)}\n')

# Category usage frequency
cat_counts = Counter(t.get('category_id') for t in real)
print('=== Category usage (non-transfer transactions), most used first ===')
for cat_id, count in cat_counts.most_common():
    name = category_name.get(cat_id, '(uncategorized)')
    print(f'{count:5d}  {name}')

# Normalize payee text to spot merchant clusters
def normalize(payee):
    if not payee:
        return None
    p = payee
    p = re.sub(r'^\d{4}-\d{2}-\d{2}:\s*', '', p)  # leading date
    p = re.sub(r'\s+in\s+[A-Z ]+,\s*[A-Z]{2}$', '', p)  # trailing city, state
    p = re.sub(r'#\s*-?\d+', '', p)  # store numbers
    p = re.sub(r'\*[A-Z0-9]+', '', p)  # processor suffixes like *5Q3GC9WD0
    p = re.sub(r'\d{3,}', '', p)  # long digit runs (phone numbers, ids)
    p = re.sub(r'\s+', ' ', p).strip().upper()
    return p

payee_counts = Counter(normalize(t.get('import_payee_name_original')) for t in real)
payee_counts.pop(None, None)
print('\n=== Most frequent normalized payees (top 80) ===')
for payee, count in payee_counts.most_common(80):
    print(f'{count:5d}  {payee}')

print(f'\nDistinct normalized payees total: {len(payee_counts)}')
