"""YouTube Data API v3: auto-discover candidates + fetch their data (quota-aware path)."""
import config
from googleapiclient.discovery import build


def _youtube():
    return build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)


def get_creators(brief, max_candidates=None):
    yt = _youtube()
    max_candidates = max_candidates or config.DISCOVER_MAX_RESULTS
    q = " ".join(brief.get("keywords", [])[:3])

    # 1. Discover candidates: paginate through video search results, collecting the
    #    unique channels behind them until we have enough candidates or run out of pages.
    channel_ids = []
    page_token = None
    for _ in range(config.DISCOVER_MAX_PAGES):
        params = {"part": "snippet", "q": q, "type": "video",
                  "maxResults": 50, "relevanceLanguage": "en"}
        if page_token:
            params["pageToken"] = page_token
        resp = yt.search().list(**params).execute()
        for item in resp.get("items", []):
            cid = item["snippet"]["channelId"]
            if cid not in channel_ids:
                channel_ids.append(cid)
            if len(channel_ids) >= max_candidates:
                break
        if len(channel_ids) >= max_candidates:
            break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    channel_ids = channel_ids[:max_candidates]
    if not channel_ids:
        return []

    # 2. Channel info + uploads playlist (the API caps `id` at 50 per call, so chunk it).
    channels = {}
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i:i + 50]
        ch = yt.channels().list(part="snippet,statistics,contentDetails",
                                id=",".join(chunk)).execute()
        for c in ch.get("items", []):
            channels[c["id"]] = c

    creators = []
    for cid in channel_ids:
        if cid not in channels:
            continue
        item = channels[cid]
        handle = item["snippet"].get("customUrl", "") or item["snippet"]["title"]
        subs = int(item["statistics"].get("subscriberCount", 0))
        if subs < config.MIN_SUBSCRIBERS:
            continue
        uploads = (item["contentDetails"]["relatedPlaylists"].get("uploads", "")
                   if "contentDetails" in item else "")
        vids = _get_videos(yt, uploads)
        if len(vids) < 3:
            continue  # too little data to compute stability/consistency
        creators.append({"handle": handle, "subscriber_count": subs, "videos": vids})
    return creators


def _get_videos(yt, uploads_playlist, max_videos=20):
    if not uploads_playlist:
        return []
    ids = []
    resp = yt.playlistItems().list(part="contentDetails", playlistId=uploads_playlist,
                                   maxResults=max_videos).execute()
    for it in resp.get("items", []):
        vid = it["contentDetails"].get("videoId")
        if vid:
            ids.append(vid)
    if not ids:
        return []
    v = yt.videos().list(part="snippet,statistics", id=",".join(ids)).execute()
    out = []
    for it in v.get("items", []):
        st = it.get("statistics", {})
        sn = it.get("snippet", {})
        out.append({
            "video_id": it["id"],
            "title": sn.get("title", ""),
            "description": sn.get("description", ""),
            "tags": sn.get("tags", []),
            "view_count": int(st.get("viewCount", 0)),
            "like_count": int(st.get("likeCount", 0)),
            "comment_count": int(st.get("commentCount", 0)),
            "published_at": sn.get("publishedAt", ""),
        })
    return out
