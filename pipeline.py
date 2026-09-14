"""Pipeline orchestration: brief -> score -> cutoff -> rank -> budget -> results."""
from datetime import datetime

import config
import scoring
import llm
import pricing


def _assign_scores(kept, score_key, values, reverse=False):
    """Normalize a metric across the candidate pool to 0-100 and write it into each creator.

    None values (insufficient data, e.g. a CV with <2 samples) get the neutral score;
    the rest are min-max normalized together. reverse=True flips the direction for
    "smaller is better" metrics (CV-based stability/consistency).
    """
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    if not indexed:
        out = [float(config.NEUTRAL_SCORE)] * len(values)
    else:
        normed = scoring.normalize_pool([v for _, v in indexed], 0.0, 100.0, reverse=reverse)
        out = [float(config.NEUTRAL_SCORE)] * len(values)
        for (i, _), n in zip(indexed, normed):
            out[i] = n
    for r, n in zip(kept, out):
        r.setdefault("scores", {})[score_key] = round(n, 2)


def run_pipeline(campaign_input, creators, mode="DEMO"):
    now = datetime.now()
    kept, excluded = [], []

    for c in creators:
        vids = c["videos"]

        # Raw quantitative metrics (the CV-based ones may be None on insufficient data).
        er = scoring.engagement_rate(vids)
        stab_cv = scoring.engagement_stability(vids)
        interval_mean, interval_std = scoring.upload_interval_stats(vids)
        interval_cv = scoring.upload_consistency(vids)
        growth = scoring.view_growth(vids, now)               # clipped, feeds the score
        growth_ratio = scoring.view_growth_ratio(vids, now)   # unclipped, for display
        avg_views = pricing.avg_recent_views(c)
        days_since = scoring.days_since_last_upload(vids, now)

        # --- Hard cutoffs, stage 1: data-driven (free, no LLM call) ---
        # These two use stats we already computed above, so they run first and drop
        # obviously-unusable candidates before we spend an LLM call on them. Each
        # rejection lands in `excluded` with a human-readable reason string.
        if days_since is not None and days_since > config.INACTIVE_DAYS:
            excluded.append({"handle": c["handle"],
                             "reason": f"inactive ({days_since}d since last upload)"})
            continue
        if avg_views < config.MIN_AVG_VIEWS:
            excluded.append({"handle": c["handle"],
                             "reason": f"low_reach (avg {avg_views:,.0f} views)"})
            continue

        # --- Hard cutoffs, stage 2: LLM-based (need the qualitative score) ---
        # These depend on score_creator()'s output, so they run right after it.
        # Order: brand safety + competitor conflict first (non-negotiable), then
        # content/audience fit (weaker, tuned conservatively so good-but-niche
        # creators aren't over-filtered).
        llm_res = llm.score_creator(c, campaign_input)
        if llm_res["risk_score"] >= config.RISK_CUTOFF:
            excluded.append({"handle": c["handle"],
                             "reason": f"brand_safety (risk={llm_res['risk_score']})"})
            continue
        if config.EXCLUDE_COMPETITOR and llm_res["competitor_conflict"]:
            excluded.append({"handle": c["handle"], "reason": "competitor_conflict"})
            continue
        if llm_res["content_match"] < config.MIN_CONTENT_MATCH:
            excluded.append({"handle": c["handle"],
                             "reason": f"content_mismatch (content_match={llm_res['content_match']})"})
            continue
        if llm_res["audience_fit"] < config.MIN_AUDIENCE_FIT:
            excluded.append({"handle": c["handle"],
                             "reason": f"audience_mismatch (audience_fit={llm_res['audience_fit']})"})
            continue

        kept.append({
            "handle": c["handle"],
            "subscribers": c["subscriber_count"],
            "avg_views": round(avg_views, 1),
            "avg_er": round(er, 4),
            # Only the unclipped ratio is exported; the clipped one stays internal for scoring.
            "growth_clipped": growth,
            "raw": {
                "engagement_rate": er,
                "stability_cv": stab_cv,
                "upload_interval_days": interval_mean,
                "upload_interval_std_days": interval_std,
                "upload_interval_cv": interval_cv,
                "growth_ratio": growth_ratio,
            },
            "content_match": llm_res["content_match"],
            "audience_fit": llm_res["audience_fit"],
            "risk_score": llm_res["risk_score"],
            "competitor_conflict": llm_res["competitor_conflict"],
            "rationale": llm_res["rationale"],
        })

    if not kept:
        return {"mode": mode, "creators": [], "excluded": excluded,
                "portfolio": None, "brief": campaign_input}

    # LLM metrics are already 0-100; the quantitative ones need pool normalization.
    for r in kept:
        r["scores"] = {
            "content_match": round(r["content_match"], 2),
            "audience_fit": round(r["audience_fit"], 2),
        }
    _assign_scores(kept, "engagement", [r["raw"]["engagement_rate"] for r in kept], reverse=False)
    _assign_scores(kept, "growth", [r["growth_clipped"] for r in kept], reverse=False)
    _assign_scores(kept, "stability", [r["raw"]["stability_cv"] for r in kept], reverse=True)
    _assign_scores(kept, "consistency", [r["raw"]["upload_interval_cv"] for r in kept], reverse=True)

    # Weighted total (0-100).
    for r in kept:
        r["total"] = round(sum(config.WEIGHTS[k] * r["scores"][k] / 100.0
                               for k in config.WEIGHTS), 2)

    # Budget / value layer.
    cpm = config.campaign_cpm(campaign_input.get("keywords", []))
    for r in kept:
        er = r["raw"]["engagement_rate"]
        r["estimated_cost"] = pricing.estimate_cost_from_views(r["avg_views"], cpm, config.ER_BENCHMARK, er)
        r["effective_value"] = pricing.effective_value_from_views(r["avg_views"], er, config.ER_BENCHMARK, r["audience_fit"])
        r["value_per_dollar"] = round(r["effective_value"] / r["estimated_cost"], 2) if r["estimated_cost"] > 0 else 0.0

    # Rank by total.
    kept.sort(key=lambda r: r["total"], reverse=True)
    for i, r in enumerate(kept):
        r["rank"] = i + 1
        r["flags"] = {"competitor_conflict": r["competitor_conflict"], "risk": r["risk_score"]}

    portfolio = pricing.portfolio(kept, campaign_input.get("budget_cap"),
                                  campaign_input.get("target_k", 3))

    creators_out = []
    for r in kept:
        creators_out.append({
            "handle": r["handle"], "subscribers": r["subscribers"], "avg_views": r["avg_views"],
            "avg_er": r["avg_er"], "raw": r["raw"], "effective_value": r["effective_value"],
            "scores": r["scores"], "total": r["total"], "rank": r["rank"],
            "rationale": r["rationale"], "flags": r["flags"],
            "estimated_cost": r["estimated_cost"], "value_per_dollar": r["value_per_dollar"],
        })

    return {"mode": mode, "creators": creators_out, "excluded": excluded,
            "portfolio": portfolio, "cpm_assumption": cpm, "brief": campaign_input}
