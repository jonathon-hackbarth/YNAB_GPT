import requests

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v

BUDGET_ID = '930b05f0-21ec-42c1-9371-27001fedd153'  # confirmed new Fresh Start plan, hardcoded on purpose
HEADERS = {
    'accept': 'application/json',
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {env["YNAB_API_KEY"]}',
}
BASE = f'https://api.ynab.com/v1/budgets/{BUDGET_ID}'


def rename(category_id, old_label, new_name):
    resp = requests.patch(f'{BASE}/categories/{category_id}', headers=HEADERS, json={'category': {'name': new_name}})
    resp.raise_for_status()
    print(f'RENAMED  {old_label!r} -> {new_name!r}')


# Work Expenses: collapse per-person split into one generic category
rename('02575fd3-31ac-42d8-97de-ca621cd58000', 'Jon Work Expenses', 'Work Expenses')
rename('6f82c488-4455-4e78-8cc1-1bd59aa3f591', 'MB Work Expenses', 'Work Expenses')

# Personal Care: collapse per-person clothing split
rename('33aad946-7eb0-48c9-88f6-9a24aacb7d0b', 'Clothing Jon', 'Clothing')
rename('b6208b97-ebe6-4542-b387-74d9c8fb9e8b', 'Clothing MB', 'Clothing')
rename('3e97756c-837b-46be-b663-552429a811a9', 'Clothing Misc', 'Clothing')
rename('bfb447cc-2562-4fc6-a604-693beff274a9', 'Clothing Nora', 'Clothing')

# Reimbursements: finish consolidating all remaining named people
reimbursements = {
    'bce2c7ad-643a-431a-83a5-1db39b2d1b89': 'Kim',
    '1b2bc278-3d53-4f8b-8d42-5c46a188fe4e': 'Jill',
    '3369d01f-3c6e-46f0-9c57-591e6e24836e': 'Josh',
    '6db26dd9-3e56-4756-abe8-8d40ddf3291f': 'Jim',
    'e22a07d4-3ec8-4c03-9413-089732c3a37e': 'Elise',
    '8498a311-c2c3-4262-9e70-7d8a5ed3fa11': 'Jenny',
    'd2d6c2ac-042e-4196-a76e-779f724d4f9b': 'Jon (Dad)',
    '42f43671-8363-47b3-a7f8-81180e8126f6': 'Julie',
    '4a092729-fd05-4902-8c9e-8dbe86e6f37b': 'Meghan',
    'd8f93988-a446-456f-9cae-38543364ee20': 'Melanie',
    'd6f3a41c-6b8a-4e53-985d-7b66333efc7c': 'Paul',
    '32727117-686d-4cf5-9326-d2b8148e4808': 'Paul & Mary Repayment',
}
for cat_id, old_label in reimbursements.items():
    rename(cat_id, old_label, 'Reimbursements')

# Subscriptions: finish sorting all remaining individually-named services into the 3 buckets
streaming_media = {
    '9d342634-a05e-4d25-9c81-71e4c9850203': 'Audible',
    'c682d82d-9104-4daf-8142-83a9c331dc97': 'Max',
    '478e48c4-9f57-4723-bc43-dfd00e922322': 'Disney Plus / Hulu / Espn+ Bundle',
    '6c491ef4-d404-439a-b370-1e80dd6445a3': 'Paramount Plus',
    '09810cd1-3198-4414-af9a-841a04c16e31': 'Peacock',
    '0c02e56a-ac51-4702-91b5-73c1ceb6791a': 'Sirius XM',
    '21323273-51df-40bc-878c-c8273e94273b': 'YouTube Red',
}
software_digital = {
    'f700506f-c35e-415c-8b0c-c84ab28a874d': 'Minecraft',
    '1e50d841-f216-4716-b3d1-94f5ae771f6d': 'Hyundai Bluelink',
    '84aa0707-fb1f-445d-8f04-4766b630e1f2': 'Duolingo',
    '10ea9242-d0dc-4fb8-aa36-c314beed1f01': 'Microsoft Business Premium',
    '1aec05bc-ca5b-4502-a6f9-18c5ed634ef6': '1Password',
    'd6c2bf42-e998-4b21-a6a1-d5f4a1ac13bc': 'Apple One Premier',
    '89829c61-6884-4f3c-a524-78d419da26d2': 'Alarmy Premium',
    'cd7e8f80-d01c-456a-875b-44ac88bd12f2': 'Blink Security',
    '8022d232-fbb8-439f-a796-900336bbef74': 'Perplexity Pro',
    'd6f389bd-777a-4545-be2f-eb862b4545f4': 'YNAB',
}
memberships = {
    'd45f8c19-f5c3-44bd-9ad8-2345a2eb5eab': 'Weight Watchers',
    '66b9be5f-1195-433a-b0d8-c71c861c466a': 'AppleCare',
    '4007f10f-109b-4a7a-adc8-96815fdb2b3e': "Sam's Club Membership",
    'fa28a6d9-7f31-4ef5-b15b-f73e55ef7797': 'Ahima Membership',
    '9ea50881-1121-42af-a89a-206d33bd325f': 'Amazon Prime',
    'd9aaaa4d-66bb-4db4-85f4-b05bc51db1f7': 'Amex Membership',
    'd179c0c4-b0e0-4d4e-afc9-c3afe4bd4b6e': 'Costco Membership',
    '283aef9f-ae47-4a7b-95a3-a3105a474493': 'Dashpass',
    'aa64dfd2-f001-4edd-859f-b37d5a4f4371': 'David Pakman Membership',
    '6987f31f-5f10-4647-a45f-7b4f06f79411': 'True Crime & Cocktails Patreon',
    'a8406af1-fad3-4917-baf3-3fd2bfdd3dc7': "We're here to help Patreon",
}
for cat_id, old_label in streaming_media.items():
    rename(cat_id, old_label, 'Streaming & Media')
for cat_id, old_label in software_digital.items():
    rename(cat_id, old_label, 'Software & Digital Services')
for cat_id, old_label in memberships.items():
    rename(cat_id, old_label, 'Memberships')

print('\nDone.')
