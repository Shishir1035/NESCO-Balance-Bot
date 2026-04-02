"""HTTP client for the NESCO prepaid customer portal.

Handles session management and Laravel CSRF token refresh automatically.
"""
import logging
from typing import Any, Callable, Optional

import httpx

from models import CustomerInfo, MonthlyUsageReport
from parser import NescoHTMLParser

logger = logging.getLogger(__name__)

_MAX_CSRF_RETRIES = 2


class NescoClient:
    """Thin HTTP wrapper around the NESCO portal form submissions.

    Usage::

        with NescoClient() as client:
            info = client.get_customer_info("77900157")
    """

    BASE_URL = "https://customer.nesco.gov.bd"
    PANEL_URL = f"{BASE_URL}/pre/panel"

    # Bengali text values expected by the portal's submit button
    _SUBMIT_RECHARGE_HISTORY = "রিচার্জ হিস্ট্রি"
    _SUBMIT_MONTHLY_USAGE = "মাসিক ব্যবহার"

    def __init__(self, parser: Optional[NescoHTMLParser] = None) -> None:
        self._parser = parser or NescoHTMLParser()
        self._http: Optional[httpx.Client] = None
        self._csrf_token: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_customer_info(self, consumer_no: str) -> Optional[CustomerInfo]:
        """Fetch customer details and current balance for *consumer_no*."""
        return self._fetch(
            consumer_no,
            submit=self._SUBMIT_RECHARGE_HISTORY,
            parse=self._parser.parse_customer_page,
        )

    def get_monthly_usage(self, consumer_no: str) -> Optional[MonthlyUsageReport]:
        """Fetch the 6-month usage report for *consumer_no*."""
        return self._fetch(
            consumer_no,
            submit=self._SUBMIT_MONTHLY_USAGE,
            parse=lambda html: self._parser.parse_monthly_usage(html, consumer_no),
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._http:
            self._http.close()
            self._http = None

    def __enter__(self) -> "NescoClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_http(self) -> httpx.Client:
        """Return the shared HTTP client, creating it on first call."""
        if self._http is None:
            self._http = httpx.Client(
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
                },
            )
        return self._http

    def _refresh_csrf_token(self) -> None:
        """GET the panel page and cache the CSRF token from the form."""
        response = self._get_http().get(self.PANEL_URL)
        response.raise_for_status()

        token = self._parser.extract_csrf_token(response.text)
        if not token:
            raise RuntimeError("Could not extract CSRF token from portal page")

        self._csrf_token = token
        logger.debug("CSRF token refreshed")

    def _fetch(
        self,
        consumer_no: str,
        *,
        submit: str,
        parse: Callable[[str], Any],
        _attempt: int = 0,
    ) -> Any:
        """Submit the portal form and parse the response.

        Automatically refreshes the CSRF token if the server returns 419
        (token expired) or redirects to the login page. Gives up after
        *_MAX_CSRF_RETRIES* refresh attempts to avoid infinite loops.
        """
        if _attempt >= _MAX_CSRF_RETRIES:
            raise RuntimeError(
                f"Giving up after {_MAX_CSRF_RETRIES} CSRF token refresh attempts"
            )

        if not self._csrf_token:
            self._refresh_csrf_token()

        try:
            response = self._get_http().post(
                self.PANEL_URL,
                data={
                    "_token": self._csrf_token,
                    "cust_no": consumer_no.strip(),
                    "submit": submit,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.BASE_URL,
                    "Referer": self.PANEL_URL,
                },
            )
            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 419:
                # 419 = CSRF token expired; get a fresh one and retry
                logger.debug("CSRF token expired (419), refreshing")
                self._csrf_token = None
                return self._fetch(consumer_no, submit=submit, parse=parse, _attempt=_attempt + 1)
            raise

        # Server redirected to the login page — session or token was invalid
        if "login" in str(response.url).lower():
            logger.debug("Redirected to login, refreshing CSRF token")
            self._csrf_token = None
            return self._fetch(consumer_no, submit=submit, parse=parse, _attempt=_attempt + 1)

        return parse(response.text)
