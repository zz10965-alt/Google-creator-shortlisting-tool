# Creator Shortlisting - intelligent creator discovery + budget optimization

NYU SPS x Google Hackathon | Track 2 (Product & Engineering)

A brand enters a single brief and the tool runs the whole flow automatically -
**discover -> fetch data -> score -> rank -> budget optimization** - compressing hours of
manual shortlisting into minutes.

## Quick start

```bash
pip install -r requirements.txt
```

**See the results (recommended - run cell-by-cell in VS Code):** open `pipeline.ipynb`

**Run from the command line:** `python main.py`

## Environment variables (`.env`, committed to this private repo)

```bash
YOUTUBE_API_KEY=your_YouTube_Data_API_v3_key
GEMINI_API_KEY=            # optional; fill in to use Gemini for qualitative scoring
```

- `YOUTUBE_API_KEY` set -> **LIVE** mode (real data); missing -> **DEMO** mode (built-in samples).
- `GEMINI_API_KEY` set -> qualitative scoring uses Gemini; missing -> keyword/synonym fallback.

## Metric model

**Core weighted score (sums to 100%)** - every sub-score and the total are on **0-100**.

| # | Dimension | Metric | How it's computed | Weight |
|---|---|---|---|---|
| 1 | Content fit | Content Match | LLM: tone / topic / audience / format vs. the brief (0-100) | 25% |
| 2 | Engagement | Engagement Rate | Median `(likes + comments) / views` over recent videos | 20% |
| 3 | Growth | View Momentum | Mean views last 30 days / mean views prior 30 days | 15% |
| 4 | Stability | Engagement Stability | CV of engagement rate (smaller = more stable) | 15% |
| 5 | Audience | Audience Fit | LLM: does the creator's audience match the target (0-100) | 15% |
| 6 | Reliability | Upload Consistency | CV of upload interval (smaller = more regular) | 10% |

Quantitative metrics (2, 3, 4, 6) are min-max normalized across the candidate pool; the
CV-based ones (4, 6) are **reversed** so a smaller CV maps to a higher score. Raw values
(engagement %, CV, upload interval, growth ratio) are also exported for display.

**Hard cutoffs (exclusion, not weighted)** - each excluded creator appears in
`results["excluded"]` with a reason. All thresholds are configurable in `config.py`.

| Cutoff | Rule | Default threshold |
|---|---|---|
| Brand safety | LLM risk score too high | `risk_score >= 70` |
| Competitor conflict | Creator mentions a competitor | on |
| Inactive | No recent upload | `> 60` days since last upload |
| Low reach | Average views too low | `avg_views < 1000` |
| Off-topic | Content doesn't match the brief | `content_match < 20` |
| Wrong audience | Audience doesn't match the target | `audience_fit < 20` |

## Budget / value layer (separate from the score)

After ranking, each creator gets a price and a value estimate, then we pick the optimal
set for the budget with a **0/1 knapsack** (it maximizes total value, unlike a greedy
"cheapest first" pass).

| Metric | Formula | Meaning |
|---|---|---|
| Estimated cost | `(avg_views / 1000) x CPM x premium` | price per sponsored video. CPM is a niche benchmark; premium = 1.15 if engagement beats the benchmark, 0.85 if under half of it, else 1.0 |
| Effective value | `avg_views x (ER / benchmark) x (audience_fit / 100)` | expected campaign value: reach x engagement quality x audience fit |
| Value-per-dollar | `effective_value / estimated_cost` | efficiency: how much value each $1 buys |
| Portfolio | 0/1 knapsack: maximize `sum(total_score x effective_value)` within `budget_cap`, up to `target_k` creators | the optimal creator set for a given budget |

Niche CPM benchmarks ($ per 1,000 views), tunable in `config.py`: beauty 12, tech 28,
finance 30, gaming 8, fashion 15, food 10, fitness 12, default 15.

## Files

| File | Purpose |
|---|---|
| `pipeline.ipynb` | * Main deliverable: full pipeline, run cell-by-cell |
| `main.py` | CLI entry point |
| `pipeline.py` | Orchestration: score -> cutoff -> rank -> budget |
| `youtube_api.py` | YouTube Data API v3: discover candidates + fetch data |
| `scoring.py` | Quantitative metrics (ER / CV / growth / consistency) |
| `llm.py` | Gemini qualitative scoring + keyword fallback |
| `pricing.py` | Pricing + value-per-dollar + 0/1 knapsack |
| `mock.py` | Sample data (DEMO mode) |
| `config.py` | Weights / thresholds / CPM benchmarks / keys |

## Interface contract

**Input** (the frontend fills this in):
```python
campaign_input = {
    "brief": "Eco-friendly skincare, women 18-34",
    "keywords": ["clean beauty", "skincare"],
    "competitors": ["BrandX"], "risk_topics": ["political"],
    "handles": [],                        # optional
    "budget_cap": 5000, "target_k": 3, "videos_per_creator": 2,   # optional
    "weights": {...}, "thresholds": {"risk_cutoff": 70, "exclude_competitor": True},
}
```

**Output** (the backend returns this) - **0-100 scale + raw values**:
```python
results = {
  "mode": "LIVE",                       # or "DEMO"
  "creators": [
    {"handle": "@eco.amical", "subscribers": 65300, "avg_views": 15858.2, "avg_er": 0.0431,
     "raw": {"engagement_rate": 0.0431, "stability_cv": 0.16,
             "upload_interval_days": 2.2, "upload_interval_std_days": 0.8,
             "upload_interval_cv": 0.36, "growth_ratio": 1.26},   # raw values (frontend formats)
     "scores": {"content_match": 100, "engagement": 43, "growth": 39,
                "stability": 70, "audience_fit": 100, "consistency": 32},   # 0-100
     "total": 68.2, "rank": 3, "rationale": "...",                 # 0-100
     "flags": {"competitor_conflict": False, "risk": 50},
     "estimated_cost": 190.3, "effective_value": 13150.0, "value_per_dollar": 69.18}
  ],
  "portfolio": {"picks": ["@eco.amical", "@shelbizleee", "@thekelsg"],
                "total_cost": 4854, "expected_views": 404519, "expected_engagements": 15155}
}
```

### Notes on the scale & direction

- Every score and the total are on **0-100** end to end (no 0-10, no x10).
- `raw.stability_cv` and `raw.upload_interval_cv` are **coefficients of variation -
  smaller = more stable/consistent**. The `scores.stability` / `scores.consistency` fields
  already reverse this for you (small CV -> high score), so the frontend only ever sees
  "higher = better" in `scores`, while `raw` carries the true numbers for display.

## Positioning / differentiation

We don't go head-to-head with Google's YouTube Creator Partnerships (BrandConnect, a
black-box with enterprise private signals). Three differentiators:
1. **Transparent & explainable** - every score and price assumption can be broken down.
2. **Customizable weights** - weights, thresholds, CPM, and budget are all tunable.
3. **For SMBs / indie agencies** - they lack Google's enterprise signals (audience overlap,
   historical campaign data); public data + benchmark estimates serve exactly that market.
