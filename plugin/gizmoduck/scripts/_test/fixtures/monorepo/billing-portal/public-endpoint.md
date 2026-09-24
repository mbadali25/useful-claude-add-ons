---
name: "Billing Portal"
url: "https://billing.example.test"
status: "live"
purpose: "Customer billing portal: invoices, payment methods, statements."
access: "Entra SSO in front of CloudFront; WAF default action: block."
kind: "website"
owner: "Platform"
staging_url: "https://billing.staging.example.test"
additional_endpoints:
  - https://api.billing.example.test/v1
  - "https://svc:hunter2@admin.billing.example.test/"
monthly_cost_usd: 4.20
cost_basis: "CloudFront $0.19, WAFv2 $4.01. Fixture values."
---

## What it does

Fixture declaration in the reference repository's `public-endpoint.md` format:
frontmatter the inventory reads, prose it ignores.
