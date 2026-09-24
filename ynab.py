import os
import requests
from models import Transaction, Category, UpdatedTransaction
import pickle


BUDGET_ID = '930b05f0-21ec-42c1-9371-27001fedd153'  # Hackbarth Budget (post Fresh Start, 2026-09-18)
YNAB_API_KEY = os.environ['YNAB_API_KEY']
DEFAULT_HEADERS = {
    'accept': 'application/json',
    'Authorization': f'Bearer {YNAB_API_KEY}',
    'Content-Type': 'application/json',
}

def get_transactions(server_knowledge=None) -> tuple[list[Transaction], str]:
    url = f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/transactions?type=unapproved'
    if server_knowledge:
        url += f'&last_knowledge_of_server={server_knowledge}'
    resp = requests.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    data = resp.json()['data']
    return [Transaction.model_validate(t) for t in data['transactions']], data['server_knowledge']


NON_SPENDING_GROUPS = {'Internal Master Category', 'Credit Card Payments'}


def get_categories() -> list[Category]:
    resp = requests.get(
        f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/categories',
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    categories_data = resp.json()
    return [
        Category(cg['name'], c['name'], c['id'])
        for cg in categories_data['data']['category_groups']
        if cg['name'] not in NON_SPENDING_GROUPS
        for c in cg['categories']
        if not c.get('hidden') and not c.get('deleted')
    ]


def get_ready_to_assign_category() -> Category:
    """The reserved 'Inflow: Ready to Assign' category YNAB puts under Internal Master Category
    in every budget. It's excluded from get_categories() (that function only returns spending
    categories), so income transactions need this looked up separately.
    """
    resp = requests.get(
        f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/categories',
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    for cg in resp.json()['data']['category_groups']:
        if cg['name'] == 'Internal Master Category':
            for c in cg['categories']:
                if c['name'] == 'Inflow: Ready to Assign':
                    return Category(cg['name'], c['name'], c['id'])
    raise RuntimeError('Could not find the Inflow: Ready to Assign category in this budget')


def get_all_transactions() -> list[Transaction]:
    """Full transaction history (approved and unapproved), for matching refunds against the
    charge they're refunding -- get_transactions() above only sees the unapproved queue.
    """
    resp = requests.get(
        f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/transactions',
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    return [Transaction.model_validate(t) for t in resp.json()['data']['transactions']]


def get_accounts() -> list[dict]:
    resp = requests.get(
        f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/accounts',
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    return [a for a in resp.json()['data']['accounts'] if not a['closed']]


def patch_transactions(transactions: list[UpdatedTransaction]):
    resp = requests.patch(
        f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/transactions',
        headers=DEFAULT_HEADERS,
        json=dict(transactions=[t.model_dump() for t in transactions]),
    )
    resp.raise_for_status()
