from dataclasses import dataclass


@dataclass(frozen=True)
class ReportDef:
    name: str
    dimensions: list[str]
    metrics: list[str]


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
    "impressions",
    "impressionsClickThroughRate",
]

REPORTS: list[ReportDef] = [
    ReportDef(name="totals", dimensions=[], metrics=CORE_METRICS),
    ReportDef(name="daily", dimensions=["day"], metrics=CORE_METRICS),
    ReportDef(
        name="traffic_sources",
        dimensions=["insightTrafficSourceType"],
        metrics=["views", "estimatedMinutesWatched"],
    ),
    ReportDef(
        name="devices",
        dimensions=["deviceType"],
        metrics=["views", "estimatedMinutesWatched"],
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
    ),
    ReportDef(
        name="retention",
        dimensions=["elapsedVideoTimeRatio"],
        metrics=["audienceWatchRatio", "relativeRetentionPerformance"],
    ),
]
