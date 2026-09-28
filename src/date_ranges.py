from datetime import date, datetime


def analytics_date_range(published_at: str, today: date) -> tuple[str, str]:
    published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
    start = published_date.isoformat()
    end = today.isoformat()
    return start, end
