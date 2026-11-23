"""
Stripe metric definitions (so these can be sanity-checked against what
Lucy actually means by each name - the brief names them, not how to
compute them):

 - revenue_pence / new_paid_sign_ups / straight_through_payments /
   recovered_payments come from `invoice.payment_succeeded` EVENTS in the
   window, not from listing invoices by `created` - an invoice can be
   created on one day and actually paid (after a retry, or at trial end) on
   another, and "revenue" and "new paid sign-ups" should count against the
   day money actually moved. `billing_reason == "subscription_create"`
   marks a brand-new subscription's first invoice (a new paid sign-up).
   `attempt_count == 1` means it was paid first time (straight-through);
   `> 1` means it had at least one prior failed attempt before this one
   succeeded (recovered from `past_due`).
 - failed_payments is `invoice.payment_failed` events in the window.
 - churned_subscriptions / churn_reasons come from
   `customer.subscription.deleted` events - `cancellation_details.reason`
   is `None` when the user didn't pick one, tallied here as
   `no_reason_given`.
 - payments_attempted / payments_succeeded are raw Charge attempts created
   in the window (every card attempt, including retries) - the denominator
   for "payment acceptance and success rate". Deliberately a different,
   lower-level count than the invoice-based metrics above: one invoice can
   span several charge attempts.
 - total_paying_users is a point-in-time count of currently `active`
   subscriptions at the moment the job runs (not specific to the snapshot
   date) - the closest available reading to "as of yesterday end of day"
   without a dedicated point-in-time export from Stripe.

Stripe's Events API only retains ~30 days - backfilling further back than
that will come back with zeros, not an error.
"""

from __future__ import annotations

import os

import stripe

from date_utils import london_day_range_utc

_client: stripe.StripeClient | None = None


def get_stripe_client() -> stripe.StripeClient:
    global _client
    if _client is None:
        _client = stripe.StripeClient(os.environ["STRIPE_DASHBOARD_KEY"])
    return _client


def _to_unix_seconds(instant) -> int:
    return int(instant.timestamp())


def reduce_stripe_daily(
    invoice_payment_succeeded: list[dict],
    invoice_payment_failed: list[dict],
    subscriptions_deleted: list[dict],
    charges: list[dict],
    total_paying_users: int,
) -> dict:
    revenue_pence = 0
    new_paid_sign_ups = 0
    straight_through_payments = 0
    recovered_payments = 0

    for invoice in invoice_payment_succeeded:
        revenue_pence += invoice["amount_paid"]
        if invoice.get("billing_reason") == "subscription_create":
            new_paid_sign_ups += 1
        if (invoice.get("attempt_count") or 1) > 1:
            recovered_payments += 1
        else:
            straight_through_payments += 1

    churn_reasons: dict[str, int] = {}
    for subscription in subscriptions_deleted:
        reason = (subscription.get("cancellation_details") or {}).get("reason") or "no_reason_given"
        churn_reasons[reason] = churn_reasons.get(reason, 0) + 1

    payments_succeeded = sum(1 for c in charges if c.get("status") == "succeeded")

    return {
        "revenue_pence": revenue_pence,
        "new_paid_sign_ups": new_paid_sign_ups,
        "total_paying_users": total_paying_users,
        "churned_subscriptions": len(subscriptions_deleted),
        "churn_reasons": churn_reasons,
        "failed_payments": len(invoice_payment_failed),
        "payments_attempted": len(charges),
        "payments_succeeded": payments_succeeded,
        "straight_through_payments": straight_through_payments,
        "recovered_payments": recovered_payments,
    }


def fetch_stripe_daily_raw(date_str: str) -> dict:
    client = get_stripe_client()
    start_utc, end_utc_exclusive = london_day_range_utc(date_str)
    created = {"gte": _to_unix_seconds(start_utc), "lt": _to_unix_seconds(end_utc_exclusive)}

    succeeded_events = list(client.v1.events.list({"type": "invoice.payment_succeeded", "created": created, "limit": 100}).auto_paging_iter())
    failed_events = list(client.v1.events.list({"type": "invoice.payment_failed", "created": created, "limit": 100}).auto_paging_iter())
    deleted_events = list(client.v1.events.list({"type": "customer.subscription.deleted", "created": created, "limit": 100}).auto_paging_iter())
    charges = list(client.v1.charges.list({"created": created, "limit": 100}).auto_paging_iter())
    total_paying_users = sum(1 for _ in client.v1.subscriptions.list({"status": "active", "limit": 100}).auto_paging_iter())

    return reduce_stripe_daily(
        invoice_payment_succeeded=[e["data"]["object"] for e in succeeded_events],
        invoice_payment_failed=[e["data"]["object"] for e in failed_events],
        subscriptions_deleted=[e["data"]["object"] for e in deleted_events],
        charges=charges,
        total_paying_users=total_paying_users,
    )
