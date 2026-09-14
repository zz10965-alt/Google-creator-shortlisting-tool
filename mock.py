"""Built-in sample data: fallback when there's no key or the API fails, so the full
pipeline still runs end-to-end."""
from datetime import datetime, timedelta


def _v(title, views, likes, comments, days_ago, tags=None, now=None):
    now = now or datetime.now()
    return {"video_id": "v", "title": title, "description": title,
            "tags": tags or [], "view_count": int(views), "like_count": int(likes),
            "comment_count": int(comments),
            "published_at": (now - timedelta(days=days_ago)).isoformat()}


def _make(handle, subs, base_views, er, cadence=3, n=20, tag=None, growth=1.0, words="video"):
    now = datetime.now()  # single reference so upload intervals are exact whole days
    videos = []
    for i in range(n):
        days_ago = i * cadence
        g = growth if days_ago < 30 else 1.0
        views = base_views * g * (1 + (n - i) * 0.01)
        likes = views * er
        videos.append(_v(f"{words} {i}", views, likes, likes * 0.08, days_ago, [tag], now=now))
    return {"handle": handle, "subscriber_count": subs, "videos": videos}


def get_creators():
    return [
        _make("@cleanbeauty_lily", 128000, 52000, 0.09, 3, 20, "skincare", 1.4, "clean beauty skincare routine"),
        _make("@techreview_tom", 980000, 210000, 0.03, 7, 20, "tech", 0.8, "gadget review"),
        _make("@glowup_mia", 64000, 30000, 0.11, 2, 20, "makeup", 1.6, "makeup tutorial"),
        _make("@health_dan", 220000, 80000, 0.05, 14, 20, "fitness", 1.0, "fitness workout"),
        _make("@competitor_fan", 150000, 60000, 0.06, 4, 20, "skincare", 1.2, "skincare featuring BrandX promo"),
        _make("@edgy_creator", 300000, 120000, 0.07, 5, 20, "skincare", 1.1, "controversial political skincare"),
    ]
