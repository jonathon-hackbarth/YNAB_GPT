# YNAB Categorizer — workflow rules

## Never run `main.py` directly without approval

`main.py` writes categories and sets flags directly in YNAB (a real, shared budget). Running it is
NOT reversible through this tool (categories/flags must be fixed by hand in the YNAB app).

**Required sequence whenever asked to "run the categorizer":**

1. Run `dry_run.py` (reads YNAB, calls Claude, but writes nothing to YNAB). It prints a table of
   proposed NEW/CORRECTED categorizations plus any items needing manual attention.
2. Show that table to the user as-is and wait for explicit approval (a clear "yes"/"go ahead" —
   not just silence or an unrelated reply).
3. Only after approval, run `main.py` to actually apply the changes.

Do not skip step 1/2 because the request sounds routine ("run it", "categorize my transactions",
etc.) — that phrasing is exactly what triggered the skip last time. The dry run is cheap (a few
thousand Claude tokens) so there's no cost reason to shortcut it.

`apply_category_plan.py` is a separate one-off script for bulk category *renames* (not transaction
categorization) — unrelated to this workflow, but same principle applies: it's a hand-authored plan
applied deliberately, not something to run speculatively.
