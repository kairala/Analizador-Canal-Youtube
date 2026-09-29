import json

from src.report_data import compute_channel_averages, load_video_documents


def test_load_video_documents_reads_all_json_files(tmp_path):
    por_video = tmp_path / "por_video"
    por_video.mkdir()
    (por_video / "vid1.json").write_text(json.dumps({"video": {"id": "vid1"}}), encoding="utf-8")
    (por_video / "vid2.json").write_text(json.dumps({"video": {"id": "vid2"}}), encoding="utf-8")

    documents = load_video_documents(tmp_path)

    assert len(documents) == 2
    assert {d["video"]["id"] for d in documents} == {"vid1", "vid2"}


def test_load_video_documents_returns_empty_list_when_directory_missing(tmp_path):
    assert load_video_documents(tmp_path) == []


def test_compute_channel_averages_averages_core_metrics_across_videos():
    documents = [
        {
            "totals": {
                "views": 100,
                "estimatedMinutesWatched": 500,
                "averageViewDuration": 30,
                "averageViewPercentage": 40.0,
                "likes": 10,
                "comments": 2,
                "shares": 1,
                "subscribersGained": 3,
                "subscribersLost": 0,
            }
        },
        {
            "totals": {
                "views": 300,
                "estimatedMinutesWatched": 1500,
                "averageViewDuration": 50,
                "averageViewPercentage": 60.0,
                "likes": 30,
                "comments": 6,
                "shares": 3,
                "subscribersGained": 9,
                "subscribersLost": 2,
            }
        },
    ]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 200
    assert averages["subscribersLost"] == 1


def test_compute_channel_averages_ignores_videos_without_totals_data():
    # A video published shortly before extraction has no Analytics data yet
    # (~48h reporting lag) — its `totals` comes back as `{}`, not an error.
    # It must not be counted as a zero-views video and dilute the average.
    documents = [{"totals": {"views": 100}}, {"totals": {}}]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 100
    assert averages["likes"] == 0


def test_compute_channel_averages_ignores_videos_with_missing_totals_key():
    documents = [{"totals": {"views": 100}}, {"video": {"id": "no-data-yet"}}]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 100


def test_compute_channel_averages_returns_zeros_for_no_documents():
    averages = compute_channel_averages([])

    assert averages["views"] == 0
    assert averages["likes"] == 0


def test_compute_channel_averages_returns_zeros_when_no_video_has_data():
    documents = [{"totals": {}}, {"totals": {}}]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 0
    assert averages["likes"] == 0


def test_compute_channel_averages_with_single_video_returns_its_own_totals():
    documents = [{"totals": {"views": 42, "likes": 5}}]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 42
    assert averages["likes"] == 5
