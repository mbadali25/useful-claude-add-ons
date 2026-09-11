# Flat Regression Report

**Hosts with findings:** 1  
**Total finding instances:** 3

| Severity | Count | In this report |
|---|---:|---|
| Critical | 1 | itemised |
| High | 0 | itemised |
| Medium | 1 | itemised |
| Low | 0 | count only |
| Info | 1 | count only |

_1 finding below Medium were recorded and are not itemised. They are inventory - version banners, DNS records, the presence of a form - rather than remediation work. The full detail remains in the JSONL._

## Findings requiring action (2)

### 1. Example CMS - Remote Code Execution - Critical

| | |
|---|---|
| Template | `CVE-2023-12345` |
| Type | http |
| CVSS | 9.8 |
| CVE | CVE-2023-12345 |
| Detections | 1 |

**Detail**

Example CMS versions before 4.2.1 allow unauthenticated remote code execution via crafted upload.

**Affected**

- `https://example.com/upload.php`

**Remediation**

Upgrade to Example CMS 4.2.1 or later.

**References**

- https://nvd.nist.gov/vuln/detail/CVE-2023-12345

### 2. Generic Login Panel Detection - Medium

| | |
|---|---|
| Template | `exposed-panel-generic` |
| Type | http |
| CVSS | n/a |
| CVE | - |
| Detections | 1 |

**Detail**

A generic login panel was detected on the host.

**Affected**

- `https://example.com/admin/login`
