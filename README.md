# Box Office Calendar

Scrapes the Box Office Mojo domestic release calendar, generates an iCalendar `.ics` file for the next year of releases, writes it locally, and uploads it to S3.

## Requirements

- Python `3.14`
- `uv`
- AWS credentials available through the normal AWS SDK resolution chain

## Environment variables

- `BOXOFFICE_S3_BUCKET`: destination S3 bucket
- `BOXOFFICE_S3_KEY`: destination object key, for example `calendar/boxoffice-releases.ics`
- `BOXOFFICE_S3_ENDPOINT_URL`: optional custom S3-compatible endpoint URL
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
export BOXOFFICE_S3_ENDPOINT_URL=https://s3.us-east-1.amazonaws.com
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
  -e BOXOFFICE_S3_ENDPOINT_URL=https://s3.us-east-1.amazonaws.com \
  -e AWS_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID=... \
  -e AWS_SECRET_ACCESS_KEY=... \
  boxoffice-calendar
```

## Kubernetes

Example manifests are included at [k8s/boxoffice-calendar-configmap.yaml](/Users/galonsky/boxoffice/k8s/boxoffice-calendar-configmap.yaml) and [k8s/boxoffice-calendar-cronjob.yaml](/Users/galonsky/boxoffice/k8s/boxoffice-calendar-cronjob.yaml).

Update the placeholder values in the ConfigMap, then apply the resources with `kubectl`:

```bash
kubectl apply -f k8s/boxoffice-calendar-configmap.yaml
kubectl apply -f k8s/boxoffice-calendar-cronjob.yaml
```

That creates:

- a `ConfigMap` named `boxoffice-calendar-config`
- a `CronJob` named `boxoffice-calendar` that runs every day at `9:00 AM` in `America/New_York`

To verify the resources:

```bash
kubectl get configmap boxoffice-calendar-config
kubectl get cronjob boxoffice-calendar
kubectl describe cronjob boxoffice-calendar
```

If you want to remove them later:

```bash
kubectl delete -f k8s/boxoffice-calendar-cronjob.yaml
kubectl delete -f k8s/boxoffice-calendar-configmap.yaml
```

## CircleCI

The repo includes CircleCI config at [.circleci/config.yml](/Users/galonsky/boxoffice/.circleci/config.yml). On every branch, CircleCI will:

1. install `uv`
2. run `uv sync`
3. run `uv run pytest`
4. build the container image
5. push the image with two tags:
   - the sanitized branch name
   - the short git SHA

Set these project environment variables in CircleCI:

- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`
- `DOCKER_IMAGE_REPOSITORY`

Example `DOCKER_IMAGE_REPOSITORY` values:

- `yourdockerhubuser/boxoffice-calendar`
- `ghcr.io/your-org/boxoffice-calendar`

## Notes

- The generated calendar is modern iCalendar (`.ics`), which is what calendar subscription clients expect.
- The uploaded object uses `Content-Type: text/calendar; charset=utf-8`.
- Public subscription access is expected to come from bucket policy, CloudFront, or equivalent infrastructure outside this script.
