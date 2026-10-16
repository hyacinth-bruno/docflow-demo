# Billing design note (not implemented in this demo)

I haven't shipped a Stripe subscription lifecycle in production, so I'm not
going to fake one here. This is how I'd approach it, based on patterns I
have shipped: the dual-layer caching / async job handling in the Jira
roadmap tool at Redcare, and the idempotency + retry logic in this repo's
`queue_sim.py`.

**Source of truth is Stripe, not the app DB.** The app DB (Mongo, in
NotarNow's stack) stores a projection of subscription state, kept in sync by
webhooks (`customer.subscription.updated`, `invoice.payment_failed`, etc.),
not by writes made at checkout time. Checkout/plan-switch requests trigger a
Stripe API call and update local state optimistically, but the webhook is
the actual reconciliation point — the same "don't trust the write path,
trust the confirmation" pattern as the idempotent queue consumer in this repo.

**Idempotency on webhooks.** Stripe delivers webhooks at-least-once. Every
handler needs to be safe to run twice for the same event ID — store
processed event IDs (same shape as `_seen_idempotency_keys` in
`queue_sim.py`) and short-circuit on replay.

**Proration and schedules.** For plan switches and consolidated
subscriptions, I'd lean on Stripe's own proration and
`subscription_schedules` rather than computing proration manually — the
places I've seen billing bugs come from re-deriving math Stripe already
does correctly.

**Testing.** Stripe's test-clock feature for simulating time-based billing
events (trial end, renewal) in integration tests, rather than mocking the
Stripe client directly — closer to testing the actual contract.

**What I'd want to pair on in the first 30 days:** how NotarNow currently
handles webhook replay/ordering and what "consolidated subscriptions"
means concretely in your model, since that's the part of the spec I can't
fully reverse-engineer from the JD alone.
