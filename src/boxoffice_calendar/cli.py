from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

import requests

from .core import (
    build_ics,
    collect_releases,
    content_hash,
    release_uid,
    required_env,
    resolve_output_path,
    upload_calendar_to_s3,
    write_calendar_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an iCalendar file from the Box Office Mojo release calendar."
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Write the calendar file to disk without uploading it to S3.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    start_date = date.today()
    end_date = start_date + timedelta(days=365)
    output_path = resolve_output_path()
    bucket = None if args.local_only else required_env("BOXOFFICE_S3_BUCKET")
    key = None if args.local_only else required_env("BOXOFFICE_S3_KEY")

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; boxoffice-calendar/0.1; "
                    "+https://www.boxofficemojo.com/calendar/)"
                )
            }
        )
        releases = collect_releases(session, start_date=start_date, end_date=end_date)

    ics_contents = build_ics(releases, generated_at=datetime.now(tz=UTC))
    write_calendar_file(ics_contents, output_path)

    if args.local_only:
        logging.info(
            "Generated %s events into %s (%s)",
            len(releases),
            output_path,
            content_hash(ics_contents)[:12],
        )
    else:
        upload_calendar_to_s3(ics_contents, bucket=bucket, key=key)
        logging.info(
            "Generated %s events into %s and uploaded to s3://%s/%s (%s)",
            len(releases),
            output_path,
            bucket,
            key,
            content_hash(ics_contents)[:12],
        )
    logging.debug("First event UID: %s", release_uid(releases[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
