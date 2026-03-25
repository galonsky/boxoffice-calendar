from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from boxoffice_calendar.core import (
    Release,
    ScrapeError,
    build_ics,
    collect_releases,
    month_starts_between,
    parse_calendar_page,
    release_uid,
    upload_calendar_to_s3,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "calendar_sample.html"


def test_parse_calendar_page_extracts_release_rows() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    releases = parse_calendar_page(
        html, "https://www.boxofficemojo.com/calendar/2026-03-01/"
    )

    assert [release.title for release in releases] == [
        "Kontinental '25",
        "Marc by Sofia",
        "Teenage Mutant Ninja Turtles II: The Secret of the Ooze",
    ]
    assert releases[0].release_date == date(2026, 3, 27)
    assert releases[0].distributor == "Oscilloscope"
    assert releases[0].scale == "Limited"
    assert releases[1].distributor is None
    assert releases[2].scale is None


def test_parse_calendar_page_raises_when_table_missing() -> None:
    with pytest.raises(ScrapeError):
        parse_calendar_page("<html><body>missing</body></html>", "https://example.com")


def test_month_starts_between_covers_date_window() -> None:
    months = month_starts_between(date(2026, 3, 25), date(2026, 6, 10))

    assert months == [
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
        date(2026, 6, 1),
    ]


def test_collect_releases_filters_window_and_deduplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")

    class StubSession:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, timeout: int) -> Mock:
            self.calls.append(url)
            response = Mock()
            response.text = html
            response.raise_for_status = Mock()
            return response

    session = StubSession()
    releases = collect_releases(
        session,
        start_date=date(2026, 3, 28),
        end_date=date(2026, 4, 2),
    )

    assert [release.title for release in releases] == [
        "Teenage Mutant Ninja Turtles II: The Secret of the Ooze"
    ]
    assert len(session.calls) == 2


def test_release_uid_is_stable() -> None:
    release = Release(
        title="Project Hail Mary",
        release_date=date(2026, 3, 20),
        distributor="Amazon MGM Studios",
        scale="Wide",
        source_url="https://www.boxofficemojo.com/release/rl123/",
    )

    assert release_uid(release) == release_uid(release)


def test_build_ics_outputs_all_day_events() -> None:
    release = Release(
        title="Project Hail Mary",
        release_date=date(2026, 3, 20),
        distributor="Amazon MGM Studios",
        scale="Wide",
        source_url="https://www.boxofficemojo.com/release/rl123/",
    )

    contents = build_ics([release], generated_at=datetime(2026, 3, 25, 12, 30, tzinfo=UTC))

    unfolded = contents.replace("\r\n ", "")

    assert "BEGIN:VCALENDAR" in unfolded
    assert "SUMMARY:Project Hail Mary" in unfolded
    assert "DTSTART;VALUE=DATE:20260320" in unfolded
    assert "DTEND;VALUE=DATE:20260321" in unfolded
    assert "Distributor: Amazon MGM Studios" in unfolded
    assert "Scale: Wide" in unfolded


def test_upload_calendar_to_s3_sets_calendar_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr("boxoffice_calendar.core.boto3.client", lambda service: client)

    upload_calendar_to_s3("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", "bucket-name", "key.ics")

    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "bucket-name"
    assert kwargs["Key"] == "key.ics"
    assert kwargs["ContentType"] == "text/calendar; charset=utf-8"
