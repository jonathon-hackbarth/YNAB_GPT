import anthropic


client = anthropic.Anthropic()

usage_completion_tokens = 0
usage_prompt_tokens = 0
usage_total_tokens = 0


def categorize(category_names: list[str], name: str, retries: int) -> str:
    prompt = f'You are a financial assistant, and are tasked with categorizing expenditures. The categories are {category_names}. I give the title of a credit card purchase, and you respond with only the category. Do not add anything else to the response, just the category.'
    claude_category = None
    for i in range(retries):
        if claude_category not in category_names:
            claude_category = _call(prompt, name, max_tokens=100)
    return claude_category


def sanity_check(merchant: str, category: str) -> tuple[bool, str]:
    """Judges whether a merchant/category pairing looks plausible or like a likely mistake
    (e.g. a password manager assigned to a "Gifts" category). Returns (is_plausible, reason);
    reason is empty when plausible.
    """
    prompt = (
        'You are sanity-checking budget categorization rules before they are hardcoded '
        'permanently. Given a merchant name and the category it has consistently been '
        'assigned to in the past, judge whether that pairing makes real-world sense. '
        'Respond on a single line in exactly this format: "PLAUSIBLE" if it makes sense, '
        'or "QUESTIONABLE: <reason under 12 words>" if it looks like a mistake. '
        'Nothing else in the response.'
    )
    text = _call(prompt, f'Merchant: {merchant}\nCategory: {category}', max_tokens=60)
    if text.strip().upper().startswith('PLAUSIBLE'):
        return True, ''
    reason = text.split(':', 1)[1].strip() if ':' in text else text.strip()
    return False, reason


def _call(prompt: str, name: str, max_tokens: int) -> str:
    global usage_completion_tokens, usage_prompt_tokens, usage_total_tokens
    response = client.messages.create(
      model="claude-haiku-4-5-20251001",
      max_tokens=max_tokens,
      system=prompt,
      messages=[
        {"role": "user", "content": name},
      ]
    )
    if response.usage is not None:
        usage_completion_tokens += response.usage.output_tokens
        usage_prompt_tokens += response.usage.input_tokens
        usage_total_tokens += response.usage.output_tokens + response.usage.input_tokens
    return response.content[0].text
