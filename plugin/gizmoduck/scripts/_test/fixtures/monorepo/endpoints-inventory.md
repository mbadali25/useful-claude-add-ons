# Endpoints inventory

<!-- gizmoduck endpoints inventory, format 1. Generated - do not edit. -->

> **Generated, do not edit.** Built by gizmoduck from each module's own
> `public-endpoint.md` declaration, or by endpoint autodetection where a module
> declares nothing. To change a row, edit the declaration (or the code), then run
> `python3 "$GIZMODUCK_HOME/scripts/gizmoduck_ci.py" inventory --repo .`
> and commit the result. A pipeline check fails while this file is stale.

> **These are declarations and static detections, not observations.** Nothing that
> built this file contacted an endpoint. `undetermined` means no staging URL could be
> read from the repository; it is never guessed.

This file carries no generation date on purpose: it is a pure function of the
repository, so it changes only when an endpoint does. Provenance is git history.

## Summary

| Measure | Count |
| --- | ---: |
| Modules | 2 |
| Declared (`public-endpoint.md`) | 1 |
| Autodetected | 1 |
| Endpoints | 6 |
| Modules with no endpoint (UNVERIFIED) | 0 |

## billing-portal

Declared in `billing-portal/public-endpoint.md`: **Billing Portal** (website, live).

| Endpoint | Source | Staging URL |
| --- | --- | --- |
| `https://***@admin.billing.example.test/` | declared - `billing-portal/public-endpoint.md` | not declared |
| `https://api.billing.example.test/v1` | declared - `billing-portal/public-endpoint.md` | not declared |
| `https://billing.example.test` | declared - `billing-portal/public-endpoint.md` | `https://billing.staging.example.test` |

## orders-api

Autodetected (no declaration). Staging base: `https://orders.staging.example.test` (detected, medium - orders-api/appsettings.Staging.json).

| Endpoint | Source | Staging URL |
| --- | --- | --- |
| `GET /api/orders` | detected, high - `orders-api/Controllers/OrdersController.cs` | `https://orders.staging.example.test/api/orders` |
| `POST /api/orders` | detected, high, protected - `orders-api/Controllers/OrdersController.cs` | `https://orders.staging.example.test/api/orders` |
| `GET /api/orders/{id}` | detected, high - `orders-api/Controllers/OrdersController.cs` | `https://orders.staging.example.test/api/orders/{id}` |
