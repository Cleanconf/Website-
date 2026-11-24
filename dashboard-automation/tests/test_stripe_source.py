from unittest.mock import patch

from sources.stripe_source import fetch_stripe_daily_raw, reduce_stripe_daily


class RestrictedStripeObject(dict):
    """
    Stands in for the real Stripe SDK's resource objects: supports `[]` and
    `.to_dict()`, but deliberately has no `.get()` - reproducing the actual
    bug this guards against (stripe-python 17.x raises AttributeError if
    you call `.get()` on one of these instead of subscripting or converting
    first; a plain dict used directly in tests would never catch that).
    """

    def to_dict(self) -> dict:
        return dict(self)

    def get(self, *args, **kwargs):  # noqa: D102 - exists only to be removed below
        raise AttributeError("'get' is a dict method, but this is not a dict. Use .to_dict() to convert it.")


class FakePage:
    def __init__(self, items: list):
        self._items = items

    def auto_paging_iter(self):
        return iter(self._items)


def _fake_event(event_type: str, obj: dict) -> dict:
    return {"type": event_type, "data": {"object": RestrictedStripeObject(obj)}}


class FakeEvents:
    def __init__(self, by_type: dict[str, list[dict]]):
        self._by_type = by_type

    def list(self, params: dict) -> FakePage:
        return FakePage(self._by_type.get(params["type"], []))


class FakeCharges:
    def __init__(self, items: list[dict]):
        self._items = [RestrictedStripeObject(item) for item in items]

    def list(self, _params: dict) -> FakePage:
        return FakePage(self._items)


class FakeSubscriptions:
    def __init__(self, count: int):
        self._count = count

    def list(self, _params: dict) -> FakePage:
        return FakePage([object()] * self._count)  # fetch_stripe_daily_raw only counts these, never reads fields.


class FakeClient:
    """Stands in for `StripeClient` - just enough of `client.v1.<resource>.list(...)` for `fetch_stripe_daily_raw`."""

    def __init__(self, succeeded_invoice: dict, charges: list[dict], active_subscriptions: int):
        self.v1 = self
        self.events = FakeEvents(
            {
                "invoice.payment_succeeded": [_fake_event("invoice.payment_succeeded", succeeded_invoice)] if succeeded_invoice else [],
                "invoice.payment_failed": [],
                "customer.subscription.deleted": [],
            }
        )
        self.charges = FakeCharges(charges)
        self.subscriptions = FakeSubscriptions(active_subscriptions)


def _invoice(**overrides) -> dict:
    return {"amount_paid": 0, "billing_reason": None, "attempt_count": 1, **overrides}


def _subscription(reason: str | None) -> dict:
    return {"cancellation_details": {"reason": reason}}


def _charge(status: str) -> dict:
    return {"status": status}


def test_fetch_stripe_daily_raw_handles_real_sdk_style_objects():
    """
    Regression test for a live production bug: the real Stripe SDK's
    objects support `[]` but raise AttributeError on `.get()`, which
    reduce_stripe_daily relies on for optional fields. A plain-dict fixture
    (like `_invoice()` above) can't catch this - it needs something that
    actually rejects `.get()` the way the SDK does.
    """
    fake_client = FakeClient(
        succeeded_invoice={"amount_paid": 0, "billing_reason": "subscription_create", "attempt_count": 1},
        charges=[{"status": "succeeded"}],
        active_subscriptions=0,
    )
    with patch("sources.stripe_source.get_stripe_client", return_value=fake_client):
        raw = fetch_stripe_daily_raw("2026-11-23")
    assert raw["new_paid_sign_ups"] == 1
    assert raw["payments_attempted"] == 1
    assert raw["payments_succeeded"] == 1


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
