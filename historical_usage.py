import requests
from collections import Counter

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v

headers = {'accept': 'application/json', 'Authorization': f'Bearer {env["YNAB_API_KEY"]}'}

ARCHIVED_BUDGET = '6bfa439e-65ae-4a89-9f9e-0b35b7ed5ab8'
NEW_BUDGET = '930b05f0-21ec-42c1-9371-27001fedd153'

# Historical category id -> "group/name", from the archived (old) budget
old_cat_resp = requests.get(f'https://api.ynab.com/v1/budgets/{ARCHIVED_BUDGET}/categories', headers=headers)
old_cat_resp.raise_for_status()
old_cat_name = {}
for cg in old_cat_resp.json()['data']['category_groups']:
    for c in cg['categories']:
        old_cat_name[c['id']] = f"{cg['name']}/{c['name']}"

old_tx_resp = requests.get(f'https://api.ynab.com/v1/budgets/{ARCHIVED_BUDGET}/transactions', headers=headers)
old_tx_resp.raise_for_status()
old_tx = old_tx_resp.json()['data']['transactions']
real_old_tx = [t for t in old_tx if not t.get('deleted') and not t.get('transfer_account_id')]

old_counts = Counter(old_cat_name.get(t.get('category_id'), '(none)') for t in real_old_tx)

# Map every historical "group/name" to whatever it became in the new budget, based on
# every rename/move/deletion we actually made this session. Group-only renames don't
# need an entry here since the category name itself matched unchanged.
RENAME_MAP = {
    'Family Spending/MB Spending': 'Shopping/Shopping',
    'Family Spending/Jon Spending': 'Entertainment & Activities/Entertainment & Activities',
    'Family Spending/Nora Spending': 'Hobbies & Books/Hobbies & Books',
    'Personal Care/Clothing Jon': 'Personal Care/Clothing',
    'Personal Care/Clothing MB': 'Personal Care/Clothing',
    'Personal Care/Clothing Misc': 'Personal Care/Clothing',
    'Personal Care/Clothing Nora': 'Personal Care/Clothing',
    'Work Expenses/Jon Work Expenses': 'Work Expenses/Work Expenses',
    'Work Expenses/MB Work Expenses': 'Work Expenses/Work Expenses',
    'Memberships & Subscriptions/Gym': 'Subscriptions/Memberships',
    'Memberships & Subscriptions/Netflix': 'Subscriptions/Streaming & Media',
    'Memberships & Subscriptions/Microsoft 365 Basic': 'Subscriptions/Software & Digital Services',
}
GROUP_RENAME = {
    'Memberships & Subscriptions': 'Subscriptions',
    'Sinking - Health & Wellness Fund': 'Health & Wellness',
    'Gifts & Party': 'Gifts & Celebrations',
    'Utilities & Connectivity': 'Utilities',
}
# Reimbursements group and all old Vacation categories were deleted outright; no mapping forward.
DELETED_PREFIXES = ('Reimbursements/', 'Vacation/')

mapped_counts = Counter()
for old_label, count in old_counts.items():
    if old_label == '(none)' or any(old_label.startswith(p) for p in DELETED_PREFIXES):
        continue
    if old_label in RENAME_MAP:
        mapped_counts[RENAME_MAP[old_label]] += count
        continue
    group, name = old_label.split('/', 1)
    group = GROUP_RENAME.get(group, group)
    mapped_counts[f'{group}/{name}'] += count

# Current live category structure
new_cat_resp = requests.get(f'https://api.ynab.com/v1/budgets/{NEW_BUDGET}/categories', headers=headers)
new_cat_resp.raise_for_status()

print(f"{'CURRENT CATEGORY':55} HISTORICAL USES")
for cg in new_cat_resp.json()['data']['category_groups']:
    if cg['name'] in ('Internal Master Category', 'Credit Card Payments', 'Hidden Categories'):
        continue
    for c in cg['categories']:
        label = f"{cg['name']}/{c['name']}"
        print(f"{label:55} {mapped_counts.get(label, 0)}")
