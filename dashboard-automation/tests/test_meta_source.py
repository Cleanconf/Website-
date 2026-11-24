from sources.meta_source import pick_best_ig_post, reduce_meta_daily


def _media(likes: int, comments: int, permalink: str = "https://instagram.com/p/x", **overrides) -> dict:
    return {"like_count": likes, "comments_count": comments, "permalink": permalink, **overrides}


def test_pick_best_ig_post_picks_highest_engagement():
    media = [_media(1, 0, "a"), _media(3, 2, "b", media_url="https://img/b.jpg"), _media(2, 2, "c")]
    best_post, engagement_rate = pick_best_ig_post(media, followers=50)
    assert best_post == {"permalink": "b", "likes": 3, "comments": 2, "image_url": "https://img/b.jpg"}
    assert engagement_rate == 5 / 50


def test_pick_best_ig_post_uses_thumbnail_for_video():
    media = [_media(3, 2, "b", media_type="VIDEO", media_url="https://video/b.mp4", thumbnail_url="https://img/b-still.jpg")]
    best_post, _ = pick_best_ig_post(media, followers=50)
    assert best_post["image_url"] == "https://img/b-still.jpg"


def test_pick_best_ig_post_none_when_nothing_posted():
    best_post, engagement_rate = pick_best_ig_post([], followers=50)
    assert best_post is None
    assert engagement_rate is None


def test_pick_best_ig_post_null_rate_with_zero_followers():
    best_post, engagement_rate = pick_best_ig_post([_media(1, 1)], followers=0)
    assert best_post is not None
    assert engagement_rate is None


def test_reduce_meta_daily_shape():
    raw = reduce_meta_daily(page_followers=15, ig_followers=23, ig_media_today=[_media(3, 2, "b", media_url="https://img/b.jpg")])
    assert raw["page_followers"] == 15
    assert raw["ig_followers"] == 23
    assert raw["ig_best_post"] == {"permalink": "b", "likes": 3, "comments": 2, "image_url": "https://img/b.jpg"}
    assert raw["ig_engagement_rate"] == 5 / 23
    # Known-unavailable metrics stay explicitly None, with a reason - never a fabricated number.
    assert raw["page_best_post"] is None
    assert raw["page_reach"] is None
    assert raw["ig_reach"] is None
    assert "pages_read_engagement" in raw["not_available_reasons"]["page_best_post"]
    assert "instagram_manage_insights" in raw["not_available_reasons"]["ig_reach"]
