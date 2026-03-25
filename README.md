# Box Office Calendar

Scrapes the Box Office Mojo domestic release calendar, generates an iCalendar `.ics` file for the next year of releases, writes it locally, and uploads it to S3.

## Requirements

- Python `3.14`
- `uv`
- AWS credentials available through the normal AWS SDK resolution chain

## Environment variables

- `BOXOFFICE_S3_BUCKET`: destination S3 bucket
- `BOXOFFICE_S3_KEY`: destination object key, for example `calendar/boxoffice-releases.ics`
- `BOXOFFICE_OUTPUT_PATH`: optional local output path, defaults to `./dist/boxoffice-releases.ics`

Standard AWS environment variables such as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, and `AWS_REGION` are supported through `boto3`.

## Local setup

Install or confirm Python `3.14`, then create the project environment with `uv`:

```bash
uv python pin 3.14
uv sync
```

Run the scraper locally:

```bash
export BOXOFFICE_S3_BUCKET=your-bucket
export BOXOFFICE_S3_KEY=calendar/boxoffice-releases.ics
uv run boxoffice-calendar
```

To generate the file locally without uploading to S3:

```bash
uv run boxoffice-calendar --local-only
```

That command will:

1. Fetch release dates from today through the next 365 days.
2. Write the calendar to `BOXOFFICE_OUTPUT_PATH` or `./dist/boxoffice-releases.ics`.
3. Upload the same file contents to `s3://$BOXOFFICE_S3_BUCKET/$BOXOFFICE_S3_KEY`.

Run tests with:

```bash
uv run pytest
```

## Container usage

Build the image with Docker or Podman:

```bash
podman build -t boxoffice-calendar .
```

Run it with environment variables:

```bash
podman run --rm \
  -e BOXOFFICE_S3_BUCKET=your-bucket \
  -e BOXOFFICE_S3_KEY=calendar/boxoffice-releases.ics \
  -e AWS_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID=... \
  -e AWS_SECRET_ACCESS_KEY=... \
  boxoffice-calendar
```

## Notes

- The generated calendar is modern iCalendar (`.ics`), which is what calendar subscription clients expect.
- The uploaded object uses `Content-Type: text/calendar; charset=utf-8`.
- Public subscription access is expected to come from bucket policy, CloudFront, or equivalent infrastructure outside this script.
