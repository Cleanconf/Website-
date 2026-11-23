from sources.stripe_source import reduce_stripe_daily


def _invoice(**overrides) -> dict:
    return {"amount_paid": 0, "billing_reason": None, "attempt_count": 1, **overrides}


def _subscription(reason: str | None) -> dict:
    return {"cancellation_details": {"reason": reason}}


def _charge(status: str) -> dict:
    return {"status": status}


def test_sums_revenue_and_counts_new_paid_sign_ups():
    raw = reduce_stripe_daily(
        invoice_payment_succeeded=[
            _invoice(amount_paid=1999, billing_reason="subscription_create"),
            _invoice(amount_paid=1999, billing_reason="subscription_cycle"),
        ],
        invoice_payment_failed=[],
        subscriptions_deleted=[],
        charges=[],
        total_paying_users=12,
    )
    assert raw["revenue_pence"] == 3998
    assert raw["new_paid_sign_ups"] == 1
    assert raw["total_paying_users"] == 12


def test_splits_straight_through_from_recovered_payments():
    raw = reduce_stripe_daily(
        invoice_payment_succeeded=[_invoice(attempt_count=1), _invoice(attempt_count=1), _invoice(attempt_count=3)],
        invoice_payment_failed=[],
        subscriptions_deleted=[],
        charges=[],
        total_paying_users=0,
    )
    assert raw["straight_through_payments"] == 2
    assert raw["recovered_payments"] == 1


def test_counts_failed_payments_and_churn_with_missing_reason():
    raw = reduce_stripe_daily(
        invoice_payment_succeeded=[],
        invoice_payment_failed=[_invoice(), _invoice()],
        subscriptions_deleted=[_subscription("too_expensive"), _subscription(None), _subscription("too_expensive")],
        charges=[],
        total_paying_users=0,
    )
    assert raw["failed_payments"] == 2
    assert raw["churned_subscriptions"] == 3
    assert raw["churn_reasons"] == {"too_expensive": 2, "no_reason_given": 1}


def test_counts_charge_attempts_and_successes_separately():
    raw = reduce_stripe_daily(
        invoice_payment_succeeded=[],
        invoice_payment_failed=[],
        subscriptions_deleted=[],
        charges=[_charge("succeeded"), _charge("succeeded"), _charge("failed")],
        total_paying_users=0,
    )
    assert raw["payments_attempted"] == 3
    assert raw["payments_succeeded"] == 2
