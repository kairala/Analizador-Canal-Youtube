import time

from googleapiclient.errors import HttpError

from src.retry import with_retry


def list_channel_videos(youtube_service, sleep=time.sleep) -> list[dict]:
    channel_response = with_retry(
        lambda: youtube_service.channels().list(part="contentDetails", mine=True).execute(),
        retry_on=(HttpError,),
        sleep=sleep,
    )
    uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = []
    page_token = None
    while True:
        response = with_retry(
            lambda: youtube_service.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute(),
            retry_on=(HttpError,),
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

    durations = _fetch_durations(youtube_service, [v["id"] for v in videos], sleep)
    for video in videos:
        video["duration"] = durations.get(video["id"], "")

    return videos


def _fetch_durations(youtube_service, video_ids: list[str], sleep) -> dict[str, str]:
    durations = {}
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start : start + 50]
        if not batch:
            continue
        response = with_retry(
            lambda: youtube_service.videos().list(part="contentDetails", id=",".join(batch)).execute(),
            retry_on=(HttpError,),
            sleep=sleep,
        )
        for item in response.get("items", []):
            durations[item["id"]] = item["contentDetails"]["duration"]
    return durations
