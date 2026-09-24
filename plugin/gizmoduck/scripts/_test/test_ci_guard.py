"""ci_guard.py - the prod-refusal guard in front of every /gizmoduck:ci endpoint scan.

Must-block and must-allow cases for each rule R1-R9 (see the module docstring).
Nothing here touches the network: redirect cases use an injected fake fetcher.

SABOTAGE-TEST before trusting a change here: reintroduce a rule's bug in a
scratch copy of ci_guard.py (drop the userinfo check, make R7 a suffix match,
ignore the port, skip IDNA, ignore allow_production, stop re-checking redirect
hops, check staging before production, strip instead of refusing whitespace,
admit a credential query parameter, disable audit_findings...) and confirm the
matching case below goes red, then restore the copy.
"""
import ci_guard as g
import pytest

STAGING = ["https://staging.example.com"]
PROD = ["https://www.example.com"]


def policy(**kw):
    kw.setdefault("staging_urls", STAGING)
    kw.setdefault("production_urls", PROD)
    return g.Policy.build(**kw)


@pytest.mark.parametrize("url,rule", [
    ("https://www.example.com/", "R8"),                       # production, no opt-in
    ("https://staging.example.com.evil.com/", "R7"),          # lookalike suffix
    ("https://evil.com/staging.example.com", "R7"),           # staging in the path
    ("https://staging-example.com/", "R7"),
    ("https://example.com/", "R7"),                           # parent domain
    ("https://api.staging.example.com/", "R7"),               # subdomain is not the origin
    ("https://staging@evil/", "R3"),                          # userinfo
    ("https://staging.example.com@evil.com/", "R3"),
    ("https://user:pw@staging.example.com/", "R3"),
    ("https://staging.example.com:8443/", "R7"),              # different port
    ("http://staging.example.com/", "R7"),                    # different scheme/port
    ("ftp://staging.example.com/", "R1"),
    ("javascript:alert(1)", "R1"),
    ("//staging.example.com/", "R1"),
    ("https://staging.example.com\\@evil.com/", "R2"),        # backslash
    ("https://staging.example.com evil/", "R2"),
    ("https://staging.example.com\t/", "R2"),
    ("", "R2"),
    ("https://staging.exаmple.com/", "R7"),              # Cyrillic a - IDNA lookalike
    ("https://" + "a" * 64 + ".example.com/", "R4"),          # label too long for IDNA
    ("https://staging.example.com:99999/", "R5"),
    ("https://staging.example.com:0/", "R5"),
    ("https://127.0.0.1/", "R6"),
    ("https://[::1]/", "R6"),
    ("https://localhost/", "R6"),
    ("https://app.localhost/", "R6"),
    ("https://2130706433/", "R6"),                            # decimal IPv4
    ("https://0x7f.1/", "R6"),                                # hex/short IPv4
    ("https://169.254.169.254/latest/meta-data/", "R6"),      # cloud metadata
])
def test_must_block(url, rule):
    d = g.check_target(url, policy())
    assert not d.allowed, f"{url!r} was allowed: {d}"
    assert d.rule == rule, f"{url!r}: expected {rule}, got {d.rule} ({d.reason})"


@pytest.mark.parametrize("url", [
    "https://staging.example.com",
    "https://staging.example.com/",
    "https://staging.example.com/api/users?id=1",
    "https://STAGING.Example.COM./api",                       # case + trailing dot
    "https://staging.example.com:443/path",                   # explicit default port
])
def test_must_allow_staging(url):
    d = g.check_target(url, policy())
    assert d.allowed, d
    assert d.origin == "https://staging.example.com:443"


def test_production_needs_both_list_and_opt_in():
    listed_only = g.check_target("https://www.example.com/", policy(allow_production=False))
    opt_in_only = g.check_target("https://www.example.com/",
                                 policy(production_urls=[], allow_production=True))
    both = g.check_target("https://www.example.com/", policy(allow_production=True))
    assert (listed_only.allowed, opt_in_only.allowed, both.allowed) == (False, False, True)
    assert (listed_only.rule, opt_in_only.rule, both.rule) == ("R8", "R7", "R8")


def test_production_opt_in_does_not_admit_a_prod_lookalike():
    d = g.check_target("https://www.example.com.evil.com/", policy(allow_production=True))
    assert not d.allowed and d.rule == "R7"


def test_idna_forms_compare_equal():
    p = policy(staging_urls=["https://bücher.example"])
    assert g.check_target("https://xn--bcher-kva.example/x", p).allowed
    assert g.check_target("https://BÜCHER.example./", p).allowed


def test_ip_literal_configured_as_staging_still_needs_the_ip_allow_list():
    p = policy(staging_urls=["http://10.0.0.5:8080"])
    assert g.check_target("http://10.0.0.5:8080/", p).rule == "R6"
    p2 = policy(staging_urls=["http://10.0.0.5:8080"], ip_allowed_urls=["http://10.0.0.5:8080"])
    assert g.check_target("http://10.0.0.5:8080/", p2).allowed


def test_ip_allow_list_alone_does_not_make_a_target():
    p = policy(ip_allowed_urls=["http://10.0.0.9"])
    d = g.check_target("http://10.0.0.9/", p)
    assert not d.allowed and d.rule == "R7"


def test_no_staging_origin_is_a_configuration_error():
    with pytest.raises(g.GuardError):
        g.Policy.build(staging_urls=[])


def test_unparseable_configured_origin_is_an_error_not_a_skip():
    with pytest.raises(g.GuardError):
        g.Policy.build(staging_urls=["https://staging.example.com", "ftp://x"])


def _fetcher(chain):
    """chain: {url: (status, location)}; anything absent answers 200."""
    calls = []

    def fetch(url):
        calls.append(url)
        return chain.get(url, (200, None))
    fetch.calls = calls
    return fetch


def test_redirect_within_staging_is_allowed():
    fetch = _fetcher({"https://staging.example.com/": (302, "/login"),
                      "https://staging.example.com/login": (301, "https://staging.example.com/home")})
    d = g.check_redirects("https://staging.example.com/", policy(), fetch=fetch)
    assert d.allowed, d
    assert fetch.calls[-1] == "https://staging.example.com/home"


@pytest.mark.parametrize("location", [
    "https://www.example.com/",                    # production
    "https://staging.example.com.evil.com/",       # lookalike
    "https://staging.example.com@evil.com/",       # userinfo
    "//evil.com/",                                 # scheme-relative
    "http://127.0.0.1/",                           # IP literal
])
def test_redirect_off_the_allowed_set_is_refused(location):
    fetch = _fetcher({"https://staging.example.com/": (302, location)})
    d = g.check_redirects("https://staging.example.com/", policy(), fetch=fetch)
    assert not d.allowed and d.rule == "R9", d


def test_redirect_refused_at_the_second_hop():
    fetch = _fetcher({"https://staging.example.com/": (302, "/a"),
                      "https://staging.example.com/a": (302, "https://evil.com/")})
    d = g.check_redirects("https://staging.example.com/", policy(), fetch=fetch)
    assert not d.allowed and d.rule == "R9"


def test_redirect_loop_is_refused():
    fetch = _fetcher({"https://staging.example.com/": (302, "/"),})
    d = g.check_redirects("https://staging.example.com/", policy(), fetch=fetch, max_hops=3)
    assert not d.allowed and "more than 3 redirects" in d.reason


def test_probe_failure_refuses_rather_than_passing():
    def boom(url):
        raise OSError("connection refused")
    d = g.check_redirects("https://staging.example.com/", policy(), fetch=boom)
    assert not d.allowed and d.rule == "R9"


def test_redirect_check_never_probes_a_refused_url():
    fetch = _fetcher({})
    d = g.check_redirects("https://evil.com/", policy(), fetch=fetch)
    assert not d.allowed and fetch.calls == []


# --- round-2 fixes: production wins, refuse-not-strip, redaction, post-scan audit ---

def test_origin_on_both_lists_is_production_and_needs_the_opt_in():
    p = g.Policy.build(staging_urls=["https://prod.example"], production_urls=["https://prod.example"],
                       allow_production=False)
    d = g.check_target("https://prod.example/", p)
    assert not d.allowed and d.rule == "R8", d
    both = g.Policy.build(staging_urls=["https://prod.example"], production_urls=["https://prod.example"],
                          allow_production=True)
    assert g.check_target("https://prod.example/", both).allowed


@pytest.mark.parametrize("url", [
    " https://staging.example.com",                      # leading ASCII space
    "https://staging.example.com ",                      # trailing ASCII space
    "https://staging.example.com/\u00a0",                # NBSP
    "\u3000https://staging.example.com/",                # ideographic space
    "https://staging.example.com/\u2028",                # line separator
    "https://staging.example.com\u200b/",                # zero-width space (format char)
    "https://staging.example.com/\u202e",                # bidi override
    "https://staging.example.com/\ufeff",                # BOM
])
def test_unicode_and_edge_whitespace_is_refused_not_stripped(url):
    d = g.check_target(url, policy())
    assert not d.allowed and d.rule == "R2", d


@pytest.mark.parametrize("url", [
    "https://staging.example.com/cb?token=SECRETVALUE",
    "https://staging.example.com/?api_key=SECRETVALUE&id=1",
    "https://staging.example.com/?X-Amz-Signature=SECRETVALUE",
    "https://staging.example.com/?password=SECRETVALUE",
])
def test_credential_query_parameters_are_refused_and_never_echoed(url):
    d = g.check_target(url, policy())
    assert not d.allowed and d.rule == "R3", d
    assert "SECRETVALUE" not in d.reason


def test_userinfo_refusal_does_not_echo_the_password():
    d = g.check_target("https://alice:SECRETVALUE@staging.example.com/", policy())
    assert not d.allowed and d.rule == "R3" and "SECRETVALUE" not in d.reason


def test_non_credential_query_parameters_still_pass():
    assert g.check_target("https://staging.example.com/api?id=1&page=2", policy()).allowed


@pytest.mark.parametrize("url,expected", [
    ("https://alice:pw@host.example/x", "https://***@host.example/x"),
    ("https://host.example/cb?token=abc&id=1", "https://host.example/cb?token=***&id=1"),
    ("https://host.example/cb?id=1", "https://host.example/cb?id=1"),
    ("https://host.example/?access_token=a&Signature=b", "https://host.example/?access_token=***&Signature=***"),
])
def test_redact_url(url, expected):
    assert g.redact_url(url) == expected


def test_redact_text_masks_every_url_in_free_text():
    text = "refused https://u:SECRET@a.example/ then http://b.example/?token=SECRET2 end"
    out = g.redact_text(text)
    assert "SECRET" not in out and "a.example" in out and "b.example" in out


def test_audit_passes_findings_on_the_staging_origin():
    recs = [{"matched_at": "https://staging.example.com/login?next=/x%20y", "host": "staging.example.com"},
            {"matched-at": "https://STAGING.example.com:443/a"},
            {"matched_at": "staging.example.com:443", "tool": "testssl"}]
    assert g.audit_findings(recs, policy()) == []


@pytest.mark.parametrize("recorded", [
    "https://www.example.com/admin",               # a scanner followed a redirect to production
    "https://evil.com/",
    "http://127.0.0.1/",
    "https://u:SECRETVALUE@staging.example.com/",
])
def test_audit_fails_any_recorded_request_that_left_the_origin(recorded):
    bad = g.audit_findings([{"matched_at": recorded}], policy())
    assert len(bad) == 1 and "SECRETVALUE" not in bad[0][1]


def test_probe_answered_differently_than_the_scanner_is_caught_by_the_audit():
    """The server returns 200 to the guard's probe and 302 to production for the
    scanner: the probe passes, and only the post-scan audit can see it."""
    fetch = _fetcher({"https://staging.example.com/": (200, None)})
    assert g.check_redirects("https://staging.example.com/", policy(), fetch=fetch).allowed
    scanner_recorded = [{"template_id": "x", "matched_at": "https://www.example.com/"}]
    assert g.audit_findings(scanner_recorded, policy())
