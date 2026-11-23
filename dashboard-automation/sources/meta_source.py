"""
Metric definitions, and what is and is not actually available with the
existing Meta token (the "Publisher" system user already used by the
content automation - see automation/README.md):

 - page_followers / ig_followers: point-in-time follower counts
   (`fan_count` on the Page, `followers_count` on the Instagram Business
   account). Both work with the existing token. "Followers gained" is not
   a separate field here - these are 'last'-kind metrics in rollups.py, so
   the comparison engine already gives the day-over-day change for free.
 - ig_best_post / ig_engagement_rate: the Instagram post from this London
   date with the most engagement (likes + comments), and that post's
   engagement rate (engagement / followers). Works with the existing
   token. `None` on a day OSO did not post to Instagram - not a 0, since
   there is nothing to measure.
 - Facebook Page posts/engagement (best post, engagement rate) and reach
   for both platforms are NOT available with the current token:
    - Facebook: `/{page}/posts` returned "(#10) This endpoint requires the
      'pages_read_engagement' permission or the 'Page Public Content
      Access' feature" - the token does not actually have working
      pages_read_engagement despite automation/README.md listing it as
      granted; worth checking in Meta Business Settings.
    - Instagram reach: `/{ig-user}/insights?metric=reach` returned
      "(#10) Application does not have permission for this action" -
      needs the `instagram_manage_insights` scope added to the token.
    - Facebook Page reach/impressions: every Insights metric name tried
      (`page_fan_adds`, `page_impressions`, `page_impressions_unique`)
      returned "(#100) The value must be a valid insights metric" even
      with a token that otherwise works - not a permissions error, so
      something about how the Page Insights API itself is being called
      needs more investigation before this can be trusted.
   These come back as `None` with a `not_available_reason` explaining
   which of the above applies, rather than a fabricated number.
"""

from __future__ import annotations

import os
from datetime import datetime

import requests

from date_utils import london_day_range_utc

GRAPH_API = "https://graph.facebook.com/v21.0"

PAGE_INSIGHTS_NOT_AVAILABLE = (
    "Facebook Page posts/engagement need the pages_read_engagement permission "
    "(or Page Public Content Access) actually working for this token - check Meta Business Settings."
)
IG_REACH_NOT_AVAILABLE = "Instagram reach needs the instagram_manage_insights permission added to this token."
PAGE_REACH_NOT_AVAILABLE = "Facebook Page reach/impressions: the Insights API call did not return a valid metric - needs further investigation."


def _get(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    body = response.json()
    if "error" in body:
        raise RuntimeError(f"Meta Graph API error: {body['error'].get('message')}")
    return body


def _fetch_page_followers() -> int:
    page_id = os.environ["META_PAGE_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]
    body = _get(f"{GRAPH_API}/{page_id}", {"fields": "fan_count", "access_token": token})
    return body["fan_count"]


def _fetch_ig_followers() -> int:
    ig_id = os.environ["META_IG_USER_ID"]
    token = os.environ["META_IG_ACCESS_TOKEN"]
    body = _get(f"{GRAPH_API}/{ig_id}", {"fields": "followers_count", "access_token": token})
    return body["followers_count"]


def _fetch_ig_media_for_date(date_str: str) -> list[dict]:
    """Instagram media whose `timestamp` falls within the London day `date_str`. Paginates until it runs past the start of that day."""
    ig_id = os.environ["META_IG_USER_ID"]
    token = os.environ["META_IG_ACCESS_TOKEN"]
    start_utc, end_utc_exclusive = london_day_range_utc(date_str)

    media_in_range = []
    url = f"{GRAPH_API}/{ig_id}/media"
    params = {"fields": "id,timestamp,like_count,comments_count,permalink", "limit": 25, "access_token": token}

    for _ in range(10):  # bounded - a single day's posts are never more than a handful of pages away
        body = _get(url, params)
        items = body.get("data", [])
        if not items:
            break
        stop = False
        for item in items:
            posted_at = datetime.fromisoformat(item["timestamp"])
            if start_utc <= posted_at < end_utc_exclusive:
                media_in_range.append(item)
            elif posted_at < start_utc:
                stop = True  # media is newest-first; anything older than the window means we are past it
        if stop:
            break
        next_url = body.get("paging", {}).get("next")
        if not next_url:
            break
        url, params = next_url, {}  # the `next` URL already carries every param, including the token

    return media_in_range


def pick_best_ig_post(media_today: list[dict], followers: int) -> tuple[dict | None, float | None]:
    """Pure selection logic: the post with the most engagement (likes + comments) from a day's media, and its engagement rate. `(None, None)` if nothing was posted that day."""
    if not media_today:
        return None, None
    best = max(media_today, key=lambda m: m["like_count"] + m["comments_count"])
    engagement = best["like_count"] + best["comments_count"]
    best_post = {"permalink": best["permalink"], "likes": best["like_count"], "comments": best["comments_count"]}
    engagement_rate = (engagement / followers) if followers else None
    return best_post, engagement_rate


def reduce_meta_daily(page_followers: int, ig_followers: int, ig_media_today: list[dict]) -> dict:
    ig_best_post, ig_engagement_rate = pick_best_ig_post(ig_media_today, ig_followers)

    return {
        "page_followers": page_followers,
        "ig_followers": ig_followers,
        "ig_best_post": ig_best_post,
        "ig_engagement_rate": ig_engagement_rate,
        "page_best_post": None,
        "page_engagement_rate": None,
        "page_reach": None,
        "ig_reach": None,
        "not_available_reasons": {
            "page_best_post": PAGE_INSIGHTS_NOT_AVAILABLE,
            "page_engagement_rate": PAGE_INSIGHTS_NOT_AVAILABLE,
            "page_reach": PAGE_REACH_NOT_AVAILABLE,
            "ig_reach": IG_REACH_NOT_AVAILABLE,
        },
    }


def fetch_meta_daily_raw(date_str: str) -> dict:
    return reduce_meta_daily(
        page_followers=_fetch_page_followers(),
        ig_followers=_fetch_ig_followers(),
        ig_media_today=_fetch_ig_media_for_date(date_str),
    )
