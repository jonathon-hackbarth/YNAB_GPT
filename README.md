# YNAB Claude Categorizer
Oh YNAB, you presume too much. The idea - brilliant. The app - [it insists upon itself](https://youtu.be/mYAi5aI_NPc?si=HaQmCC_toGnjEQr6&t=21). Every other app that costs ~100 $/mo automates, visualizes, and summarizes far better. 

Fine! YOU WIN! I do, in fact, need a budget... 

This repo uses Claude (Anthropic's LLM) to auto-categorize transactions, and mark them with a visible blue flag in-app. State between runs is serialized to a local SQLite DB to avoid unnecessary API calls.

> Forked from [aelzeiny/YNAB_GPT](https://github.com/aelzeiny/YNAB_GPT) and adapted to use Claude instead of OpenAI.

![marked with a blue flag image](./docs/ynab-flag.png)

## Instructions
Transactions already tagged with categories will not be considered.

Uncategorized transactions will attempt to be matched to Categories that fall in Category-Groups that start with "[Auto]" (case-insensitive).

![category groups that start with auto image](./docs/ynab-categories.png)

In the example shown in the image, the categories eligible for auto-categorization are "Entertainment", "Dining", "Shopping", and "Gas".

Transactions that have been auto-categorized are marked with a blue flag.

## Setup

### Prerequisites
* Python 3.12+
* A [YNAB API key](https://api.ynab.com/#personal-access-tokens)
* An [Anthropic API key](https://console.anthropic.com/settings/keys)

### Installation
```
git clone https://github.com/jonathon-hackbarth/YNAB_GPT.git
cd YNAB_GPT
pip install -r requirements.txt
cp .env.example .env  # then fill in your keys
```

Export your environment variables (or load them from `.env`) before running:
```
export YNAB_API_KEY=your_ynab_api_key_here
export ANTHROPIC_API_KEY=your_anthropic_api_key_here
python main.py
```

## Cost
You'll need to bring your own Anthropic API key. At the moment Claude 3.5 Sonnet is $3 / 1M input tokens, and $15 / 1M output tokens [[pricing page](https://www.anthropic.com/pricing)]. For me, each uncategorized transaction uses about ~85 input tokens, and ~2 output tokens. All things considered, very cheap.

YNAB is 99 $/yr, and you don't pay any extra for an API key. You're rate-limited for 200 requests per hour. Each script run uses 3 requests. Meaning you can run this script every minute if you want.

## Build & Deployment

Docker
```
docker build -t aelzeiny/ynab-gpt .
docker run \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -e YNAB_API_KEY=$YNAB_API_KEY \
    -v ./db.sqlite:/app/db.sqlite \
    aelzeiny/ynab-gpt
```

Crontab, every 5 minutes (absolute paths recommended)
```
crontab -e
*/1 * * * * docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -e YNAB_API_KEY=$YNAB_API_KEY -v ./db.sqlite:/app/db.sqlite aelzeiny/ynab-gpt > path_to_logs.log
```

## Unsolicited App Reviews
I spent time in `YNAB`, `Copilot`, and `Monarch` and came out with a clear winner for my existing needs. Copilot was a VERY close second.
I tried 3 apps for a few weeks, and here are my opinions.
* `YNAB` -> **Best** for Budgeting. It’s in the name. **But** I wish it automated more.
* `Copilot` -> **Best** for visualizations, auto-categorization, recurring expense tracking, dashboards, and overviews. But I wish it was better at budgeting and goals.
* `Monarch` -> **Most** well-rounded. But I wish it did better at auto-categorization & recurring expenses & budgets instead of targets.
