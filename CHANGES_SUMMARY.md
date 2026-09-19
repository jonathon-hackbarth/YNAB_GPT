# Changes Summary: OpenAI → Claude Conversion

This document details the changes made to convert this fork of [aelzeiny/YNAB_GPT](https://github.com/aelzeiny/YNAB_GPT) from using OpenAI's ChatGPT to Anthropic's Claude for transaction categorization.

## File-by-file changes

### `requirements.txt`
- Replaced the `openai` package with `anthropic`.

### `gpt.py`
- Replaced `from openai import OpenAI` with `import anthropic`.
- Changed client instantiation from `client = OpenAI()` to `client = anthropic.Anthropic()`.
- Rewrote `_categorize()` to call `client.messages.create()` instead of `client.chat.completions.create()`:
  - `model` is now `"claude-3-5-sonnet-20241022"`.
  - Added the required `max_tokens=100` parameter (the Anthropic Messages API requires this; OpenAI's Chat Completions API does not).
  - The system prompt is passed via the top-level `system=prompt` parameter instead of a `{"role": "system", ...}` message — Claude's Messages API keeps system instructions separate from the conversational message list.
  - Only the `user` message remains in the `messages` list.
  - Token usage accounting now reads `response.usage.output_tokens` and `response.usage.input_tokens` instead of `response.usage.completion_tokens` and `response.usage.prompt_tokens`. `usage_total_tokens` is computed as their sum, since the Anthropic API does not return a combined total directly.
  - Response text is now read from `response.content[0].text` instead of `response.choices[0].message.content`, reflecting Claude's content-block response structure.
- Renamed the `gpt_category` local variable to `claude_category` in both `categorize()` and (via `main.py`) its caller, for clarity.

### `main.py`
- Updated `categorize_transactions()` to use the renamed `claude_category` variable.
- Changed the console output header from `"ChatGPT Usage:"` to `"Claude Usage:"`.
- Relabeled the printed usage lines from `"Completion Tokens:"` / `"Prompt Tokens:"` to `"Output Tokens:"` / `"Input Tokens:"`, matching Anthropic's terminology (the underlying variable names, imported from `gpt.py`, are unchanged for compatibility with `db.py`).

### `ynab.py`
- Removed a leftover `import pdb; pdb.set_trace()` debugging breakpoint from `patch_transactions()`, which would have paused execution and hung any non-interactive (e.g. cron/Docker) run.

### `README.md`
- Retitled from "YNAB ChatGPT Categorizer" to "YNAB Claude Categorizer".
- Replaced references to ChatGPT/OpenAI with Claude/Anthropic throughout.
- Added a note crediting the original repository this was forked from.
- Updated the Cost section with Claude 3.5 Sonnet pricing.
- Updated Docker run/crontab examples to use `ANTHROPIC_API_KEY` instead of `OPENAI_API_KEY`.
- Added a Setup section covering prerequisites and installation steps.

### `.env.example` (new)
- Added a template listing the two required environment variables: `YNAB_API_KEY` and `ANTHROPIC_API_KEY`.

## Claude vs. ChatGPT: what changed under the hood

| | OpenAI (original) | Anthropic Claude (this fork) |
|---|---|---|
| SDK | `openai` | `anthropic` |
| Client | `OpenAI()` | `anthropic.Anthropic()` |
| Call | `client.chat.completions.create()` | `client.messages.create()` |
| Model | `gpt-3.5-turbo` | `claude-3-5-sonnet-20241022` |
| Max tokens | optional | required (`max_tokens`) |
| System prompt | message with `role: "system"` | top-level `system` parameter |
| Response text | `response.choices[0].message.content` | `response.content[0].text` |
| Usage fields | `completion_tokens`, `prompt_tokens`, `total_tokens` | `output_tokens`, `input_tokens` (no `total_tokens`; summed manually) |

Functionally, both models are used the same way in this project: given a list of candidate categories and a transaction's payee name, the model returns a single category string (or "other"). The prompting strategy, retry logic, and categorization flow in `main.py` are unchanged — only the API client and request/response shape differ.

## Setup

1. Get an [Anthropic API key](https://console.anthropic.com/settings/keys) (replaces the OpenAI API key).
2. Get a [YNAB personal access token](https://api.ynab.com/#personal-access-tokens) (unchanged from upstream).
3. Copy `.env.example` to `.env` and fill in both keys, or export them directly:
   ```
   export YNAB_API_KEY=your_ynab_api_key_here
   export ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```
4. Install dependencies: `pip install -r requirements.txt`.
5. Run: `python main.py`.

For Docker/crontab usage, see the updated examples in [README.md](./README.md#build--deployment) — the only change from upstream is the environment variable name (`ANTHROPIC_API_KEY` instead of `OPENAI_API_KEY`).

## Cost comparison

| | OpenAI `gpt-3.5-turbo` (original) | Anthropic `claude-3-5-sonnet-20241022` (this fork) |
|---|---|---|
| Input | $0.50 / 1M tokens | $3.00 / 1M tokens |
| Output | $1.50 / 1M tokens | $15.00 / 1M tokens |

Claude 3.5 Sonnet is more expensive per token than GPT-3.5 Turbo, but each transaction categorization uses very few tokens (~85 input, ~2 output), so the absolute cost difference is still negligible for typical personal-finance usage — a few cents per month even at frequent (e.g. every-minute cron) run cadences. If cost is a concern, consider switching `model` in `gpt.py` to a smaller/cheaper Claude model.

## Troubleshooting

- **`anthropic.AuthenticationError` / 401 errors**: confirm `ANTHROPIC_API_KEY` is set in the environment (or `.env`) and is valid.
- **`anthropic.BadRequestError` mentioning `max_tokens`**: this field is required by the Messages API; it's already set to `100` in `gpt.py`, but if you change the prompt or expect longer category names, increase it.
- **Empty or unexpected category responses**: check that `response.content[0].text` actually contains a plain category string — if you change the prompt to ask for more than one field, the response shape (`content` list) may contain more than one block and the code will need to be updated to handle that.
- **Script hangs with no output**: this was previously caused by a leftover `pdb.set_trace()` breakpoint in `ynab.py`, which has been removed in this fork. If you see hangs again after modifying `ynab.py`, check for similar debugging statements.
- **`ModuleNotFoundError: No module named 'anthropic'`**: run `pip install -r requirements.txt` after pulling this fork — the dependency changed from `openai` to `anthropic`.
