import logging
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


def get_sns_client():
    return boto3.client(
        "sns",
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def should_send_alert(last_alerted_at: datetime | None) -> bool:
    if last_alerted_at is None:
        return True
    cooldown = timedelta(minutes=settings.alert_cooldown_minutes)
    return datetime.utcnow() - last_alerted_at > cooldown


def send_alert(
    card_name: str,
    price: float,
    source: str,
    link: str,
    min_price: float | None,
    max_price: float | None,
) -> bool:
    try:
        client = get_sns_client()

        subject = f"[MTG Monitor] {card_name} — ${price:.2f} on {source}"
        # SNS subject max 100 chars
        if len(subject) > 100:
            subject = subject[:97] + "..."

        range_str = ""
        if min_price is not None and max_price is not None:
            range_str = f"${min_price:.2f} - ${max_price:.2f}"
        elif min_price is not None:
            range_str = f"${min_price:.2f}+"
        elif max_price is not None:
            range_str = f"Up to ${max_price:.2f}"

        body = (
            f"Card: {card_name}\n"
            f"Price: ${price:.2f}\n"
            f"Source: {source}\n"
            f"Link: {link}\n"
        )
        if range_str:
            body += f"\nYour configured range: {range_str}\n"

        client.publish(
            TopicArn=settings.sns_topic_arn,
            Subject=subject,
            Message=body,
        )

        logger.info(f"SNS alert sent: {subject}")
        return True

    except ClientError as e:
        logger.error(f"Failed to send SNS alert: {e}")
        return False
    except Exception as e:
        logger.error(f"SNS service error: {e}")
        return False


def send_test_notification() -> bool:
    try:
        client = get_sns_client()
        client.publish(
            TopicArn=settings.sns_topic_arn,
            Subject="[MTG Monitor] Test Notification",
            Message="This is a test notification from your MTG Price Monitor.",
        )
        logger.info("SNS test notification sent successfully")
        return True
    except ClientError as e:
        logger.error(f"Failed to send SNS test notification: {e}")
        return False
    except Exception as e:
        logger.error(f"SNS test notification error: {e}")
        return False
