# MTG Price Monitor

A full-stack application that monitors Magic: The Gathering card prices on **TCGPlayer**, **eBay**, and **Manapool**, with AWS SNS alerts when cards become available within your configured price range.

## Features

- **Multi-source monitoring**: TCGPlayer, eBay (Buy It Now, US only), Manapool
- **Configurable price thresholds**: Set min/max price per monitor
- **AWS SNS alerts**: Get notified when cards are in your price range
- **Alert controls**: Enable/disable alerts per monitor, 30-minute cooldown
- **Price history**: Track price trends over time with interactive charts
- **Web dashboard**: Add, edit, delete monitors via a modern React UI
- **1-minute polling**: Automatic checks every 60 seconds

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/seawhite/mtg-price-monitor.git
cd mtg-price-monitor
cp .env.example .env
# Edit .env with your AWS credentials
```

### 2. Run with Docker Compose

```bash
docker compose -f mtg-price-monitor.yml up -d
```

### 3. Access the dashboard

Open [http://localhost:6088](http://localhost:6088) in your browser.

## Pre-built Images

Pull from Docker Hub instead of building locally:

```bash
docker pull seawhite/mtg-price-monitor-backend:latest
docker pull seawhite/mtg-price-monitor-frontend:latest
```

Then run with `docker compose -f mtg-price-monitor.yml up -d`.

## AWS Setup

### 1. Create IAM User

Create an IAM user and attach the policy from `iam-policy.json`:

```bash
aws iam create-user --user-name mtg-monitor
aws iam put-user-policy --user-name mtg-monitor --policy-name MTGMonitorSNS --policy-document file://iam-policy.json
aws iam create-access-key --user-name mtg-monitor
```

### 2. Configure SNS Topic

The default topic ARN is `arn:aws:sns:us-west-2:328883027245:cwhitepersonal`. Update `SNS_TOPIC_ARN` in `.env` if using a different topic.

Make sure you have a subscription (email, SMS, etc.) on the topic.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | *(required)* | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | *(required)* | IAM user secret key |
| `AWS_DEFAULT_REGION` | `us-west-2` | AWS region |
| `SNS_TOPIC_ARN` | `arn:aws:sns:us-west-2:328883027245:cwhitepersonal` | SNS topic ARN |
| `ALERT_COOLDOWN_MINUTES` | `30` | Minutes between repeat alerts |
| `CHECK_INTERVAL_SECONDS` | `60` | Polling interval in seconds |

## Architecture

- **Frontend**: React + Vite + TailwindCSS + shadcn/ui + Recharts
- **Backend**: Python FastAPI + APScheduler + Playwright + BeautifulSoup4
- **Database**: SQLite (persisted via Docker volume at `/docker/mtg-price-monitor/data/`)
- **Notifications**: AWS SNS via boto3

## Development

### Backend (local)

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (local)

```bash
cd frontend
npm install
npm run dev
```

## Building & Pushing Docker Images

```bash
docker build -t seawhite/mtg-price-monitor-backend ./backend
docker build -t seawhite/mtg-price-monitor-frontend ./frontend
docker push seawhite/mtg-price-monitor-backend
docker push seawhite/mtg-price-monitor-frontend
```

## License

MIT
