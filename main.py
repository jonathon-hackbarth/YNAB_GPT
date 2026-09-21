import argparse
import datetime as dt
from contextlib import closing
from tqdm import tqdm

from models import Category, Transaction, UpdatedTransaction
import ynab
import gpt
import overrides
import db


NUM_GPT_RETRIES = 2
DB_PATH = './db.sqlite'
TransactionId = str


def categorize_transactions(transactions: list[Transaction], categories: list[Category]) -> dict[TransactionId, tuple[Category, bool, str]]:
    """Given a list of transactions and categories, categorize or re-categorize as many transactions
    as possible, including transactions that already have a category Claude disagrees with.
    Transfers and inflows (deposits, refunds, interest, cashback) are skipped entirely, since
    they aren't spending and have no business being forced into a spending category.

    Deterministic merchants (see overrides.py) are matched directly, skipping Claude entirely.
    For anything else, Claude is asked to override an *existing* category only requires a
    second, independent call to agree first -- a single low-confidence guess isn't enough to
    overwrite something that was already there.

    Returns: a dictionary of Transaction.id => (Category, is_override, source), for transactions
    whose category should change. is_override is True when this replaces an existing category
    rather than filling a blank one. source is 'rule' or 'claude'. Transactions Claude leaves
    unmatched, or already agrees with, are omitted.
    """
    category_map = {c.get_name().lower(): c for c in categories}
    categorized_transactions = {}
    other = 'other'
    category_names = [c.get_name().lower() for c in categories] + [other]

    for warning in overrides.validate_rules(category_map):
        print('WARNING:', warning)

    for transaction in tqdm(transactions):
        if transaction.transfer_account_id:
            continue

        if transaction.amount >= 0:
            continue

        if not transaction.import_payee_name_original:
            continue

        payee = overrides.normalize_payee(transaction.import_payee_name_original)
        had_existing_category = transaction.category_id is not None

        rule_category_name = overrides.lookup_category(payee)
        if rule_category_name is not None:
            if rule_category_name not in category_map:
                continue
            matched_category = category_map[rule_category_name]
            source = 'rule'
        else:
            claude_category = gpt.categorize(category_names, payee, retries=NUM_GPT_RETRIES)
            if claude_category not in category_map:
                continue
            matched_category = category_map[claude_category]
            source = 'claude'

            if had_existing_category and matched_category.category_id != transaction.category_id:
                second_opinion = gpt.categorize(category_names, payee, retries=NUM_GPT_RETRIES)
                if second_opinion != claude_category:
                    continue

        if matched_category.category_id == transaction.category_id:
            continue

        categorized_transactions[transaction.id] = (matched_category, had_existing_category, source)
    return categorized_transactions


def main(apply_flag=True):
    with closing(db.RunStore(DB_PATH)) as store:
        last_run = store.get_last_run()
        server_knowledge = None
        if last_run is not None:
            server_knowledge = last_run.server_knowledge
        transactions, server_knowledge = ynab.get_transactions(server_knowledge)
        categories = ynab.get_categories()
        categorized_transactions = categorize_transactions(transactions, categories)
        updated_transactions = [
            UpdatedTransaction.model_validate(t.model_dump())
            for t in transactions if t.id in categorized_transactions
        ]
        for t in updated_transactions:
            matched_category, is_override, source = categorized_transactions[t.id]
            t.category_id = matched_category.category_id
            if apply_flag:
                t.flag_color = 'purple' if is_override else 'blue'

        if updated_transactions:
            ynab.patch_transactions(updated_transactions)
        print('updated', len(updated_transactions), 'transactions')
        print('Claude Usage:')
        from gpt import usage_completion_tokens, usage_prompt_tokens, usage_total_tokens
        print('\tOutput Tokens:', usage_completion_tokens)
        print('\tInput Tokens:', usage_prompt_tokens)
        print('\tTotal Tokens:', usage_total_tokens)
        store.add_run(db.Run(
            id=None,
            dttm=dt.datetime.now(),
            completion_token_usage=usage_completion_tokens,
            prompt_token_usage=usage_prompt_tokens,
            server_knowledge=server_knowledge
        ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--no-flag', action='store_true',
        help="Don't set the blue flag on categorized transactions (e.g. after a manual dry-run review already covered them)",
    )
    args = parser.parse_args()
    main(apply_flag=not args.no_flag)
