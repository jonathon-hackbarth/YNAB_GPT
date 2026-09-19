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


def patch_transactions(transactions: list[UpdatedTransaction]):
    resp = requests.patch(
        f'https://api.ynab.com/v1/budgets/{BUDGET_ID}/transactions',
        headers=DEFAULT_HEADERS,
        json=dict(transactions=[t.model_dump() for t in transactions]),
    )
    resp.raise_for_status()
