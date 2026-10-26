"""Tests for graceful degradation when Tavily fails during verification."""
import pytest

from groundcontrol.clients import FixtureMissing, MissingApiKey, UpstreamError
from groundcontrol.clients.tavily import TavilyClient
from groundcontrol.eu261 import assess
from groundcontrol.models import FlightFacts
from groundcontrol.verify import verify


def _make_cancellation_assessment():
    facts = FlightFacts(
        flight_number="LO123",
        carrier="VQ",
        departure_airport="WAW",
        arrival_airport="CDG",
        disruption_type="cancellation",
        notice_days=2,
    )
    return assess(facts)


def test_verify_missing_api_key(monkeypatch):
    assessment = _make_cancellation_assessment()
    assert assessment.compensation is not None
    assert assessment.care
    assert assessment.refund_or_rerouting is not None

    def fake_search(*args, **kwargs):
        raise MissingApiKey("TAVILY_API_KEY environment variable is required when LIVE=1")

    monkeypatch.setattr(TavilyClient, "search", fake_search)

    result = verify(assessment)
    assert result.compensation.evidence == []
    assert all(item.evidence == [] for item in result.care)
    assert result.refund_or_rerouting.evidence == []
    assert result.compensation.status == "unverified"
    assert result.verification_error is not None
    assert "TAVILY_API_KEY" in result.verification_error


def test_verify_upstream_error(monkeypatch):
    assessment = _make_cancellation_assessment()

    def fake_search(*args, **kwargs):
        raise UpstreamError("Tavily returned HTTP 500")

    monkeypatch.setattr(TavilyClient, "search", fake_search)

    result = verify(assessment)
    assert result.compensation.evidence == []
    assert all(item.evidence == [] for item in result.care)
    assert result.refund_or_rerouting.evidence == []
    assert result.compensation.status == "unverified"
    assert result.verification_error == "Tavily returned HTTP 500"


def test_verify_first_error_kept(monkeypatch):
    assessment = _make_cancellation_assessment()
    call_count = 0

    def fake_search(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise UpstreamError(f"Tavily error #{call_count}")

    monkeypatch.setattr(TavilyClient, "search", fake_search)

    result = verify(assessment)
    assert call_count > 1
    assert result.verification_error == "Tavily error #1"


def test_verify_fixture_missing_propagates(monkeypatch):
    assessment = _make_cancellation_assessment()

    def fake_search(*args, **kwargs):
        raise FixtureMissing("Tavily fixture missing for hash 1234567890abcdef")

    monkeypatch.setattr(TavilyClient, "search", fake_search)

    with pytest.raises(FixtureMissing, match="Tavily fixture missing"):
        verify(assessment)
