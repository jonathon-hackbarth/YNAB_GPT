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


def categorize_transactions(
    transactions: list[Transaction],
    categories: list[Category],
    credit_card_accounts: list[dict] = (),
) -> tuple[dict[TransactionId, tuple[Category, bool, str]], list[db.TouchedTransaction]]:
    """Given a list of transactions and categories, categorize or re-categorize as many transactions
    as possible, including transactions that already have a category Claude disagrees with.
    Transfers and inflows (deposits, refunds, interest, cashback) are skipped entirely, since
    they aren't spending and have no business being forced into a spending category.

    A transaction whose payee exactly matches one of the user's own credit-card account names
    (e.g. "Best Buy" matching the "Best Buy CC" account) is skipped entirely with a printed
    WARNING, *unless* the transaction itself already lives on a credit-card account -- that's
    just a purchase made at that store, not a payment. Money leaving a non-card account under a
    card's own name is almost always a bill-pay that YNAB failed to auto-link as a transfer, and
    needs to be fixed by hand in the YNAB app (the API can't convert an existing transaction into
    a transfer).

    Deterministic merchants (see overrides.py) are matched directly, skipping Claude entirely.
    For anything else, Claude is asked to override an *existing* category only requires a
    second, independent call to agree first -- a single low-confidence guess isn't enough to
    overwrite something that was already there.

    Returns: (categorized, attention).
    categorized is a dict of Transaction.id => (Category, is_override, source), for transactions
    whose category should change. is_override is True when this replaces an existing category
    rather than filling a blank one. source is 'rule' or 'claude'. Transactions Claude leaves
    unmatched, or already agrees with, are omitted.
    attention is a list of TouchedTransaction rows (category_name=None) for transactions the
    tool looked at but deliberately left alone with a printed WARNING -- e.g. a likely
    credit-card bill-pay -- so those stay visible in the pending-review table instead of
    silently vanishing.
    """
    category_map = {c.get_name().lower(): c for c in categories}
    categorized_transactions = {}
    attention_items = []
    other = 'other'
    category_names = [c.get_name().lower() for c in categories] + [other]
    card_account_ids = {a['id'] for a in credit_card_accounts}
    credit_card_account_names = {overrides.normalize_account_name(a['name']) for a in credit_card_accounts}

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

        if not had_existing_category and transaction.account_id not in card_account_ids and overrides.is_likely_card_payment(payee, credit_card_account_names):
            note = 'Looks like a bill-pay to your own card -- fix by hand in YNAB as a Transfer.'
            print(f'WARNING: {payee!r} {note}')
            attention_items.append(db.TouchedTransaction(
                transaction_id=transaction.id, payee=transaction.import_payee_name_original,
                category_name=None, source='card-payment', is_override=False,
                dttm=dt.datetime.now(), note=note,
            ))
            continue

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
    return categorized_transactions, attention_items


def categorize_income(
    transactions: list[Transaction],
    ready_to_assign: Category,
) -> dict[TransactionId, tuple[Category, bool, str]]:
    """Uncategorized inflows from known income sources (paychecks, etc. -- see
    overrides.INCOME_PATTERNS) go straight to Inflow: Ready to Assign, so real income doesn't sit
    Uncategorized or get mistaken for an unmatched refund by match_refund_categories() below.
    """
    matches = {}
    for t in transactions:
        if t.transfer_account_id or t.amount <= 0 or t.category_id or not t.import_payee_name_original:
            continue
        if overrides.is_income(t.import_payee_name_original):
            matches[t.id] = (ready_to_assign, False, 'income')
    return matches


def match_refund_categories(
    transactions: list[Transaction],
    history: list[Transaction],
    categories: list[Category],
) -> tuple[dict[TransactionId, tuple[Category, bool, str]], list[db.TouchedTransaction]]:
    """Uncategorized inflows (refunds, credits, price adjustments) should be categorized the same
    as the charge they're offsetting, so they net back out of that category instead of inflating
    Ready to Assign as income. For each uncategorized inflow, finds the most recent transaction
    anywhere in `history` (the full account history, not just the unapproved queue) with the same
    normalized payee and a real spending category, and reuses it.

    Deliberately does NOT fall back to guessing by payee/category *name* similarity when no prior
    charge exists -- that's a materially weaker guarantee than actually netting against a real
    charge, and a fresh/reset budget may simply not have one yet. Those are returned as `attention`
    (see categorize_transactions()) instead of a guess.
    """
    category_by_id = {c.category_id: c for c in categories}
    most_recent_charge_by_payee = {}
    for h in history:
        if h.transfer_account_id or h.amount >= 0 or not h.category_id or not h.import_payee_name_original:
            continue
        payee = overrides.normalize_payee(h.import_payee_name_original).lower()
        existing = most_recent_charge_by_payee.get(payee)
        if existing is None or h.date > existing.date:
            most_recent_charge_by_payee[payee] = h

    matches = {}
    attention_items = []
    for t in transactions:
        if t.transfer_account_id or t.amount <= 0 or t.category_id or not t.import_payee_name_original:
            continue
        payee = overrides.normalize_payee(t.import_payee_name_original).lower()
        charge = most_recent_charge_by_payee.get(payee)
        if charge is None:
            note = 'Refund/credit with no matching prior charge -- categorize it by hand.'
            print(f'WARNING: {t.import_payee_name_original!r} {note}')
            attention_items.append(db.TouchedTransaction(
                transaction_id=t.id, payee=t.import_payee_name_original,
                category_name=None, source='refund-unmatched', is_override=False,
                dttm=dt.datetime.now(), note=note,
            ))
            continue
        matched_category = category_by_id.get(charge.category_id)
        if matched_category is None:
            continue
        matches[t.id] = (matched_category, False, 'refund-match')
    return matches, attention_items


def main(apply_flag=True):
    with closing(db.RunStore(DB_PATH)) as store:
        last_run = store.get_last_run()
        server_knowledge = None
        if last_run is not None:
            server_knowledge = last_run.server_knowledge
        transactions, server_knowledge = ynab.get_transactions(server_knowledge)
        categories = ynab.get_categories()
        credit_card_accounts = [a for a in ynab.get_accounts() if a['type'] == 'creditCard']
        ready_to_assign = ynab.get_ready_to_assign_category()
        categorized_transactions, card_attention = categorize_transactions(transactions, categories, credit_card_accounts)
        income_matches = categorize_income(transactions, ready_to_assign)
        categorized_transactions.update(income_matches)
        remaining_transactions = [t for t in transactions if t.id not in income_matches]
        refund_matches, refund_attention = match_refund_categories(remaining_transactions, ynab.get_all_transactions(), categories)
        categorized_transactions.update(refund_matches)
        attention_items = card_attention + refund_attention

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

        updated_transactions = [
            UpdatedTransaction.model_validate(t.model_dump())
            for t in transactions if t.id in categorized_transactions
        ]
        transaction_by_id = {t.id: t for t in transactions}
        touched = []
        for t in updated_transactions:
            matched_category, is_override, source = categorized_transactions[t.id]
            t.category_id = matched_category.category_id
            if apply_flag:
                if source == 'refund-match':
                    t.flag_color = 'green'
                elif source == 'income':
                    t.flag_color = 'yellow'
                else:
                    t.flag_color = 'purple' if is_override else 'blue'
            orig_t = transaction_by_id[t.id]
            payee = orig_t.import_payee_name_original
            verb = 'CORRECTED' if is_override else 'NEW'
            amount = orig_t.amount / 1000
            print(f'{orig_t.date}  ${amount:>8.2f}  {payee!r:50} {verb:>9} [{source}] -> {matched_category.full_name()}')
            touched.append(db.TouchedTransaction(
                transaction_id=t.id, payee=payee, category_name=matched_category.full_name(),
                source=source, is_override=is_override, dttm=dt.datetime.now(),
            ))

        if updated_transactions:
            ynab.patch_transactions(updated_transactions)
        if touched or attention_items:
            store.record_touched(touched + attention_items)
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
