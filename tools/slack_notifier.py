"""Slack incoming-webhook notifier.

Posts the Delegator's `notification_message` to a Slack channel via an
incoming webhook URL stored in the `SLACK_WEBHOOK_URL` env var. Follows
the same Graceful Tool Failure pattern as the rest of `tools/` —
returns an error dict instead of raising on bad input or network failure.
"""
import json
import os
from typing import TypedDict

import requests


class SlackResult(TypedDict):
    posted: bool
    status_code: int
    error: str | None


def post_to_slack(message: str, webhook_url: str | None = None) -> SlackResult:
    """Send a plain-text message to a Slack incoming webhook.

    Args:
        message: The Slack-formatted message (markdown allowed).
        webhook_url: Override the SLACK_WEBHOOK_URL env var.

    Returns:
        SlackResult with posted=True on success.
        On failure, posted=False and error explains why.

    Raises:
        Never raises — all failures are returned as error dicts.

    Example:
        >>> post_to_slack("hello from the bot")
        {'posted': True, 'status_code': 200, 'error': None}
    """
    if not isinstance(message, str) or not message.strip():
        return {"posted": False, "status_code": 0,
                "error": "message must be a non-empty string."}

    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return {"posted": False, "status_code": 0,
                "error": "SLACK_WEBHOOK_URL is not set. "
                         "Add it to your .env file or pass webhook_url explicitly."}

    if not url.startswith("https://hooks.slack.com/"):
        return {"posted": False, "status_code": 0,
                "error": "webhook_url does not look like a Slack incoming webhook URL."}

    try:
        resp = requests.post(
            url,
            data=json.dumps({"text": message}),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    except requests.Timeout:
        return {"posted": False, "status_code": 0,
                "error": "Slack webhook request timed out after 10s."}
    except requests.RequestException as e:
        return {"posted": False, "status_code": 0,
                "error": f"Network error posting to Slack: {str(e)[:200]}"}

    if resp.status_code != 200:
        return {"posted": False, "status_code": resp.status_code,
                "error": f"Slack returned HTTP {resp.status_code}: {resp.text[:200]}"}

    return {"posted": True, "status_code": 200, "error": None}
