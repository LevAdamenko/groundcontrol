"""Evidence verification against official EU legal sources using Tavily."""
from __future__ import annotations

from urllib.parse import urlparse
from groundcontrol.clients import UpstreamError
from groundcontrol.clients.tavily import TavilyClient
from groundcontrol.models import Assessment, Evidence

ALLOWED_DOMAINS: tuple[str, ...] = (
    "eur-lex.europa.eu",
    "curia.europa.eu",
    "europa.eu",
    "transport.ec.europa.eu",
    "ulc.gov.pl",
)


def _is_allowed_host(url: str) -> bool:
    try:
        host = urlparse(url).netloc.split(":")[0].lower()
        return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def filter_evidence(raw_results: list[dict], anchor: str) -> list[Evidence]:
    """Filter search results keeping only allow-listed hosts whose content contains the anchor."""
    kept: list[Evidence] = []
    for r in raw_results:
        url = r.get("url", "")
        content = r.get("content") or r.get("snippet") or ""
        title = r.get("title") or ""
        if _is_allowed_host(url) and anchor in content:
            kept.append(
                Evidence(
                    url=url,
                    title=title,
                    snippet=content,
                    anchor=anchor,
                )
            )
    return kept


def verify(assessment: Assessment) -> Assessment:
    """Verify entitlements by querying Tavily and attaching filtered official evidence."""
    if not assessment.applies:
        return assessment

    client = TavilyClient()

    def _safe_search(query: str, include_domains: list[str] | tuple[str, ...] | None = None) -> list[dict]:
        try:
            return client.search(query, include_domains=include_domains)
        except UpstreamError as exc:
            if assessment.verification_error is None:
                assessment.verification_error = str(exc)
            return []

    # 1. Verify compensation entitlement
    if assessment.compensation and assessment.compensation.amount_eur > 0:
        comp = assessment.compensation
        amount = comp.amount_eur
        if amount == 300:
            # 300 EUR reduced case: search for 600 EUR band + Sturgeon case law
            q1 = "Regulation 261 2004 EUR 600 Article 7"
            res1 = _safe_search(q1, include_domains=list(ALLOWED_DOMAINS))
            ev1 = filter_evidence(res1, "EUR 600")

            q2 = "CJEU Sturgeon C-402/07 three hours or more"
            res2 = _safe_search(q2, include_domains=["curia.europa.eu", "eur-lex.europa.eu"])
            ev2 = filter_evidence(res2, "three hours or more")
            comp.evidence = ev1 + ev2
            comp.required_anchors = ["EUR 600", "three hours or more"]
        else:
            anchor = f"EUR {amount}"
            q = f"Regulation 261 2004 EUR {amount} Article 7"
            res = _safe_search(q, include_domains=list(ALLOWED_DOMAINS))
            comp.evidence = filter_evidence(res, anchor)
            comp.required_anchors = [anchor]

    # 2. Verify care entitlements
    if assessment.care:
        care_query = "Regulation 261 2004 meals and refreshments Article 9"
        care_res = _safe_search(care_query, include_domains=list(ALLOWED_DOMAINS))
        care_ev = filter_evidence(care_res, "meals and refreshments")
        for ent in assessment.care:
            ent.evidence = list(care_ev)

    # 3. Verify refund/re-routing
    if assessment.refund_or_rerouting:
        ref_query = "Regulation 261 2004 reimbursement Article 8"
        ref_res = _safe_search(ref_query, include_domains=list(ALLOWED_DOMAINS))
        ref_ev = filter_evidence(ref_res, "reimbursement")
        assessment.refund_or_rerouting.evidence = ref_ev

    return assessment
