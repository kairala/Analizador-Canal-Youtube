import time

from src.http_retry import call_with_http_retry


def list_channel_videos(youtube_service, sleep=time.sleep) -> list[dict]:
    channel_response = call_with_http_retry(
        lambda: youtube_service.channels().list(part="contentDetails", mine=True).execute(),
        sleep=sleep,
    )
    channel_items = channel_response.get("items", [])
    if not channel_items:
        raise ValueError(
            "a conta autenticada não tem um canal do YouTube — apague token.json "
            "e faça login novamente com a conta dona do canal"
        )
    uploads_playlist_id = channel_items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = []
    page_token = None
    while True:
        response = call_with_http_retry(
            lambda: youtube_service.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute(),
            sleep=sleep,
        )
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    videos = [
        {
            "id": item["contentDetails"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["contentDetails"].get("videoPublishedAt")
            or item["snippet"]["publishedAt"],
        }
        for item in items
    ]

    details = _fetch_video_details(youtube_service, [v["id"] for v in videos], sleep)
    for video in videos:
        video_details = details.get(video["id"], {})
        video["duration"] = video_details.get("duration", "")
        video["privacy_status"] = video_details.get("privacy_status", "")

    return videos


def _fetch_video_details(youtube_service, video_ids: list[str], sleep) -> dict[str, dict]:
    details = {}
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start : start + 50]
        if not batch:
            continue
        response = call_with_http_retry(
            lambda: youtube_service.videos().list(part="contentDetails,status", id=",".join(batch)).execute(),
            sleep=sleep,
        )
        for item in response.get("items", []):
            details[item["id"]] = {
                "duration": item["contentDetails"]["duration"],
                "privacy_status": item.get("status", {}).get("privacyStatus", ""),
            }
    return details
