# Reports (Logs API) and Statistics (Metrics API)

Old APIs `Events` (/v3/{domain}/events) and `Stats` (/v3/{domain}/stats/...) are deprecated
but still answer. Prefer Logs and Metrics. Exception: `inbox` uses Events (event=stored).

## Logs - POST /v1/analytics/logs
One row per event per recipient. Retention depends on the plan.
Body: `duration` (required, e.g. `1d`, `12h`), optional `start`/`end` (RFC 2822), `events` [list],
`filter` {"AND":[{attribute, comparator "=", values:[{label,value}]}]}, `pagination`
{sort "timestamp:desc", limit <=100, token}, `include_totals`.
Filter attributes: domain, recipient, recipient_domain, recipient_provider, from, subject,
message_id, tag, event, severity, ip, ip_pool, country, device, delivery_status_code,
delivery_status_bounce_type, user_variables, subaccount.
Next page: pass `pagination.token` from the previous response via `call ... --json`.

Useful reading of a failed event: `delivery-status.code` (5xx permanent, 4xx temporary),
`delivery-status.message`, `severity` (permanent/temporary), `reason`.

## Metrics - POST /v1/analytics/metrics
Body: `duration` or `start`/`end`, `resolution` (hour/day/month), `dimensions`, `metrics`,
`filter` (same shape as logs), `include_aggregates`.
Dimensions: time, domain, tag, ip, ip_pool, recipient_domain, recipient_provider, country,
device, subaccount, bot.
Common metrics (counts): accepted_count, delivered_count, failed_count,
permanent_failed_count, temporary_failed_count, stored_count, opened_count,
unique_opened_count, clicked_count, unique_clicked_count, unsubscribed_count,
complained_count, processed_count, sent_count.
Rates: delivered_rate, opened_rate, clicked_rate, unique_opened_rate, unique_clicked_rate,
bounced_rate, permanent_failed_rate, temporary_failed_rate, complained_rate, unsubscribed_rate.
Usage/billing metrics: POST /v1/analytics/usage/metrics.

## Health thresholds (industry rules of thumb)
| Metric | Healthy | Act now |
|---|---|---|
| bounced_rate | < 2% | > 5% |
| complained_rate | < 0.1% | > 0.3% |
| delivered_rate | > 97% | < 95% |

## Other report-ish endpoints
Bounce classification: `find classification`. Tags: `find tags`. Alerts: `find alerts`.
Sending queue status: `call GET /v3/domains/{name}/sending_queues`.
