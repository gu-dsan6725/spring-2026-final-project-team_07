# Sage — Agentic AI Nutritionist

A multi-agent meal-planning app. Describe your goals and dietary needs in plain language, and Sage builds meal plans, remembers your profile between sessions, and generates shopping lists. Built for Georgetown DSAN 6725 by Tyler Blue and Andrew Moy.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/) for dependency management
- **Anthropic API key** with credits (the free tier cannot sustain the agent workload)
- **Mem0 API key** (free tier is sufficient)

## Setup

```bash
git clone https://github.com/gu-dsan6725/spring-2026-final-project-team_07.git
cd spring-2026-final-project-team_07

uv sync
cp .env.example .env
# fill in ANTHROPIC_API_KEY and MEM0_API_KEY in .env
```

## Running the app

```bash
PYTHONPATH=src uv run streamlit run app.py
```

Opens at `http://localhost:8501`.

## Usage examples

Once the app is running, try these prompts in the chat:

| Prompt | What happens |
|---|---|
| `Hi, I'm 28M, 180 lbs, 5'10", moderately active. Goal is fat loss. Peanut allergy. $3/serving budget.` | The app collects your profile and saves it so you never have to repeat it |
| `Build me a 3-day meal plan.` | Generates a plan that hits your calorie and protein targets, skipping any meals with your allergens |
| `Give me a shopping list.` | Aggregates every ingredient across the plan into a single deduplicated list |
| `What's my calorie target?` | Reports the daily target computed from your profile |
| `Rebuild it cheaper.` | Regenerates the plan under a tighter cost cap |

You can also browse recipes, manage your profile, and swap individual meals from the tabs in the app.

## Deliverables

This repo is also the project submission for DSAN 6725. Final artifacts live in `deliverables/`:

- `deliverables/paper/final_paper.pdf` — conference-style paper
- `deliverables/poster/poster.pdf` — 48" × 36" poster
- `deliverables/slides/slide_deck_print.pdf` — presentation slides
- `deliverables/demo/sage_demo.mp4` — recorded demo
