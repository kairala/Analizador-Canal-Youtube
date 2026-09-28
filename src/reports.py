from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReportDef:
    name: str
    dimensions: list[str]
    metrics: list[str]
    column_renames: dict = field(default_factory=dict)


CORE_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
]

REPORTS: list[ReportDef] = [
    ReportDef(name="totals", dimensions=[], metrics=CORE_METRICS),
    ReportDef(
        name="daily",
        dimensions=["day"],
        metrics=CORE_METRICS,
        column_renames={"day": "date"},
    ),
    ReportDef(
        name="traffic_sources",
        dimensions=["insightTrafficSourceType"],
        metrics=["views", "estimatedMinutesWatched"],
        column_renames={"insightTrafficSourceType": "source"},
    ),
    ReportDef(
        name="devices",
        dimensions=["deviceType"],
        metrics=["views", "estimatedMinutesWatched"],
        column_renames={"deviceType": "device"},
    ),
    ReportDef(
        name="geography",
        dimensions=["country"],
        metrics=["views", "estimatedMinutesWatched"],
    ),
    ReportDef(
        name="demographics",
        dimensions=["ageGroup", "gender"],
        metrics=["viewerPercentage"],
        column_renames={"ageGroup": "age_group", "viewerPercentage": "viewer_percentage"},
    ),
    ReportDef(
        name="retention",
        dimensions=["elapsedVideoTimeRatio"],
        metrics=["audienceWatchRatio", "relativeRetentionPerformance"],
        column_renames={
            "elapsedVideoTimeRatio": "elapsed_ratio",
            "audienceWatchRatio": "audience_watch_ratio",
            "relativeRetentionPerformance": "relative_retention_performance",
        },
    ),
]
