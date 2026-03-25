from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import boto3
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

BASE_URL = "https://www.boxofficemojo.com"
CALENDAR_PATH_TEMPLATE = "/calendar/{year:04d}-{month:02d}-01/"
DEFAULT_OUTPUT_PATH = Path("./dist/boxoffice-releases.ics")
LOGGER = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    """Raised when scraping fails or produces unexpected output."""


@dataclass(frozen=True, slots=True)
class Release:
    title: str
    release_date: date
    source_url: str
    distributor: str | None = None
    scale: str | None = None


def month_starts_between(start: date, end: date) -> list[date]:
    months: list[date] = []
    cursor = start.replace(day=1)
    final_month = end.replace(day=1)
    while cursor <= final_month:
        months.append(cursor)
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


def build_month_url(month_start: date) -> str:
    return urljoin(
        BASE_URL,
        CALENDAR_PATH_TEMPLATE.format(year=month_start.year, month=month_start.month),
    )


def fetch_calendar_html(session: requests.Session, month_start: date) -> str:
    url = build_month_url(month_start)
    LOGGER.info("Fetching %s", url)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def parse_calendar_page(html: str, page_url: str) -> list[Release]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.mojo-body-table")
    if table is None:
        raise ScrapeError(f"Could not find schedule table in {page_url}")

    releases: list[Release] = []
    current_date: date | None = None

    for row in table.find_all("tr", recursive=False):
        classes = row.get("class", [])
        if "mojo-group-label" in classes:
            header = row.select_one("th.mojo-table-header")
            if header is None:
                raise ScrapeError(f"Found date row without header in {page_url}")
            try:
                current_date = datetime.strptime(
                    header.get_text(" ", strip=True), "%B %d, %Y"
                ).date()
            except ValueError as exc:
                raise ScrapeError(f"Could not parse release date in {page_url}") from exc
            continue

        cells = row.find_all("td", recursive=False)
        if len(cells) != 3:
            continue
        if current_date is None:
            raise ScrapeError(f"Found release row before any date header in {page_url}")

        release_cell, distributor_cell, scale_cell = cells
        title_heading = release_cell.select_one("h3")
        if title_heading is None:
            raise ScrapeError(f"Could not find movie title in {page_url}")
        release_link = _find_release_link(release_cell)
        source_url = urljoin(BASE_URL, release_link["href"]) if release_link else page_url

        distributor = _clean_optional_text(distributor_cell)
        scale = _clean_optional_text(scale_cell)

        releases.append(
            Release(
                title=title_heading.get_text(" ", strip=True),
                release_date=current_date,
                distributor=distributor,
                scale=scale,
                source_url=source_url,
            )
        )

    if not releases:
        raise ScrapeError(f"No releases found in {page_url}")

    return releases


def _find_release_link(release_cell: Tag) -> Tag | None:
    for link in release_cell.select("a[href]"):
        href = link.get("href", "")
        if href.startswith("/release/") and link.find("h3") is not None:
            return link
    return None


def _clean_optional_text(cell: Tag) -> str | None:
    value = cell.get_text(" ", strip=True)
    if not value or value == "N/A" or value == "-":
        return None
    return value


def collect_releases(
    session: requests.Session, start_date: date, end_date: date
) -> list[Release]:
    seen: set[tuple[str, date]] = set()
    releases: list[Release] = []

    for month_start in month_starts_between(start_date, end_date):
        page_url = build_month_url(month_start)
        html = fetch_calendar_html(session, month_start)
        for release in parse_calendar_page(html, page_url):
            if not (start_date <= release.release_date <= end_date):
                continue
            dedupe_key = (release.title.casefold(), release.release_date)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            releases.append(release)

    releases.sort(key=lambda release: (release.release_date, release.title.casefold()))
    if not releases:
        raise ScrapeError(
            f"No releases found between {start_date.isoformat()} and {end_date.isoformat()}"
        )
    return releases


def release_uid(release: Release) -> str:
    identifier = f"{release.title}|{release.release_date.isoformat()}|boxofficemojo"
    return f"{uuid.uuid5(uuid.NAMESPACE_URL, identifier)}@boxoffice-calendar"


def build_ics(releases: Iterable[Release], generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(tz=UTC)
    dtstamp = generated_at.strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//boxoffice-calendar//Box Office Releases//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Box Office Releases",
        "X-WR-CALDESC:Upcoming theatrical release dates scraped from Box Office Mojo.",
    ]

    for release in releases:
        description_parts = [f"Release date: {release.release_date.isoformat()}"]
        if release.distributor:
            description_parts.append(f"Distributor: {release.distributor}")
        if release.scale:
            description_parts.append(f"Scale: {release.scale}")
        description_parts.append(f"Source: {release.source_url}")

        start_value = release.release_date.strftime("%Y%m%d")
        end_value = (release.release_date + timedelta(days=1)).strftime("%Y%m%d")

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_escape_ics_text(release_uid(release))}",
                f"DTSTAMP:{dtstamp}",
                f"SUMMARY:{_escape_ics_text(release.title)}",
                f"DTSTART;VALUE=DATE:{start_value}",
                f"DTEND;VALUE=DATE:{end_value}",
                f"DESCRIPTION:{_escape_ics_text('\\n'.join(description_parts))}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"


def write_calendar_file(contents: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(contents, encoding="utf-8", newline="")


def upload_calendar_to_s3(contents: str, bucket: str, key: str) -> None:
    endpoint_url = os.environ.get("BOXOFFICE_S3_ENDPOINT_URL")
    client_kwargs = {"endpoint_url": endpoint_url} if endpoint_url else {}
    client = boto3.client("s3", **client_kwargs)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=contents.encode("utf-8"),
        ContentType="text/calendar; charset=utf-8",
    )


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def resolve_output_path() -> Path:
    output_value = os.environ.get("BOXOFFICE_OUTPUT_PATH")
    return Path(output_value) if output_value else DEFAULT_OUTPUT_PATH


def _escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", r"\;")
        .replace(",", r"\,")
    )


def _fold_ics_line(line: str, limit: int = 75) -> str:
    if len(line) <= limit:
        return line

    segments = [line[:limit]]
    remainder = line[limit:]
    while remainder:
        segments.append(f" {remainder[: limit - 1]}")
        remainder = remainder[limit - 1 :]
    return "\r\n".join(segments)


def content_hash(contents: str) -> str:
    return hashlib.sha256(contents.encode("utf-8")).hexdigest()
