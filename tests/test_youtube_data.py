from src.youtube_data import list_channel_videos


class FakeYouTubeService:
    def __init__(self, channel_response, playlist_pages, videos_response):
        self._channel_response = channel_response
        self._playlist_pages = playlist_pages
        self._videos_response = videos_response
        self._playlist_call_count = 0
        self._last_kwargs = {}

    def channels(self):
        return self

    def playlistItems(self):
        return self

    def videos(self):
        return self

    def list(self, **kwargs):
        self._last_kwargs = kwargs
        return self

    def execute(self):
        if "playlistId" in self._last_kwargs:
            page = self._playlist_pages[self._playlist_call_count]
            self._playlist_call_count += 1
            return page
        if "id" in self._last_kwargs:
            return self._videos_response
        return self._channel_response


def test_list_channel_videos_paginates_and_merges_durations():
    channel_response = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUxxxx"}}}]
    }
    playlist_pages = [
        {
            "items": [
                {
                    "contentDetails": {"videoId": "vid1"},
                    "snippet": {"title": "Video 1", "publishedAt": "2024-01-01T00:00:00Z"},
                }
            ],
            "nextPageToken": "TOKEN2",
        },
        {
            "items": [
                {
                    "contentDetails": {"videoId": "vid2"},
                    "snippet": {"title": "Video 2", "publishedAt": "2024-02-01T00:00:00Z"},
                }
            ]
        },
    ]
    videos_response = {
        "items": [
            {"id": "vid1", "contentDetails": {"duration": "PT5M"}},
            {"id": "vid2", "contentDetails": {"duration": "PT3M"}},
        ]
    }
    service = FakeYouTubeService(channel_response, playlist_pages, videos_response)

    videos = list_channel_videos(service)

    assert videos == [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT5M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-02-01T00:00:00Z", "duration": "PT3M"},
    ]


def test_list_channel_videos_returns_empty_list_for_channel_with_no_uploads():
    channel_response = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUxxxx"}}}]
    }
    playlist_pages = [{"items": []}]
    videos_response = {"items": []}
    service = FakeYouTubeService(channel_response, playlist_pages, videos_response)

    assert list_channel_videos(service) == []
