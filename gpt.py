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
            claude_category = _categorize(prompt, name)
    return claude_category


def _categorize(prompt: str, name: str) -> str:
    global usage_completion_tokens, usage_prompt_tokens, usage_total_tokens
    response = client.messages.create(
      model="claude-haiku-4-5-20251001",
      max_tokens=100,
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
