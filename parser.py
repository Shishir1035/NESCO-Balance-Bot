"""HTML parser for the NESCO customer portal."""
import logging
import re
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from models import CustomerInfo, MonthlyUsage, MonthlyUsageReport, RechargeRecord

logger = logging.getLogger(__name__)


class NescoHTMLParser:
    """Extracts structured data from NESCO portal HTML responses."""

    def parse_customer_page(self, html: str) -> Optional[CustomerInfo]:
        """Parse the customer info page returned after submitting a consumer number.

        The portal renders a form where each field label sits in one Bootstrap
        column and the corresponding read-only <input> sits in the next column.
        We locate each label by its Bengali text and walk to the adjacent input.
        """
        soup = BeautifulSoup(html, "html.parser")

        try:
            def field(label_text: str) -> str:
                return self._get_input_after_label(soup, label_text)

            balance, balance_updated_at = self._parse_balance(soup)

            return CustomerInfo(
                customer_name=field("গ্রাহকের নাম") or "N/A",
                father_name=field("পিতা/স্বামীর নাম") or None,
                address=field("ঠিকানা") or "N/A",
                mobile=field("মোবাইল") or "N/A",
                office=field("সংশ্লিষ্ট বিদ্যুৎ অফিস") or "N/A",
                feeder=field("ফিডারের নাম") or "N/A",
                consumer_no=field("কনজ্যুমার নম্বর") or "N/A",
                meter_no=field("মিটার নম্বর") or "N/A",
                sanctioned_load=self._parse_float(field("অনুমোদিত লোড")),
                tariff=field("অনুমোদিত ট্যারিফ") or "N/A",
                meter_type=field("মিটারের ধরণ") or "N/A",
                meter_status=field("মিটার স্ট্যাটাস") or "N/A",
                installation_date=field("মিটার স্থাপনের তারিখ") or "N/A",
                min_recharge=self._parse_float(field("মিনিমাম রিচার্জের পরিমাণ")),
                balance=balance,
                balance_updated_at=balance_updated_at,
                recharge_history=self._parse_recharge_table(soup),
            )
        except Exception:
            logger.error("Failed to parse customer page", exc_info=True)
            return None

    def parse_monthly_usage(self, html: str, consumer_no: str) -> Optional[MonthlyUsageReport]:
        """Parse the monthly usage table from the portal HTML."""
        soup = BeautifulSoup(html, "html.parser")
        records: List[MonthlyUsage] = []

        for table in soup.find_all("table"):
            header = table.find("tr")
            if header and ("বছর" in header.get_text() or "মাস" in header.get_text()):
                for row in table.find_all("tr")[1:]:
                    record = self._parse_monthly_usage_row(row)
                    if record is not None:
                        records.append(record)

        return MonthlyUsageReport(consumer_no=consumer_no, records=records) if records else None

    def extract_csrf_token(self, html: str) -> Optional[str]:
        """Extract the Laravel CSRF token from a hidden form input."""
        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "_token"})
        if token_input:
            return token_input.get("value")
        return None

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_input_after_label(self, soup: BeautifulSoup, label_text: str) -> str:
        """Return the value of the <input> that follows the label with *label_text*.

        The portal uses two Bootstrap column patterns:
        - Pattern A: the <label> itself has a col-* class → the next sibling
          <div> holds the input.
        - Pattern B: the <label> is nested inside a col-* <div> → the parent
          div's next sibling holds the input.
        """
        for label in soup.find_all("label"):
            if label_text not in label.get_text(strip=True):
                continue

            # Pattern A: label has col class directly
            if label.get("class") and any("col" in c for c in label.get("class", [])):
                value = self._input_value_from_next_sibling(label)
                if value:
                    return value

            # Pattern B: label is inside a col div
            parent = label.find_parent("div", class_=re.compile(r"col"))
            if parent:
                value = self._input_value_from_next_sibling(parent)
                if value:
                    return value

        return ""

    @staticmethod
    def _input_value_from_next_sibling(element: Tag) -> str:
        """Return the value of the first form-control input in the next sibling div."""
        next_div = element.find_next_sibling("div")
        if next_div:
            inp = next_div.find("input", class_="form-control")
            if inp and inp.get("value"):
                return inp.get("value", "").strip()
        return ""

    def _parse_balance(self, soup: BeautifulSoup) -> tuple[float, str]:
        """Extract balance value and update timestamp from the balance label."""
        for label in soup.find_all("label"):
            if "অবশিষ্ট ব্যালেন্স" not in label.get_text():
                continue

            # Timestamp is in a nested <span> inside the label
            span = label.find("span")
            updated_at = span.get_text(strip=True) if span else ""

            next_div = label.find_next_sibling("div")
            if next_div:
                inp = next_div.find("input", class_="form-control")
                if inp and inp.get("value"):
                    return self._parse_float(inp.get("value")), updated_at

        return 0.0, ""

    def _parse_recharge_table(self, soup: BeautifulSoup) -> List[RechargeRecord]:
        """Parse the recharge history table, identified by the 'টোকেন' column header."""
        records: List[RechargeRecord] = []

        for table in soup.find_all("table"):
            header = table.find("tr")
            if not (header and "টোকেন" in header.get_text()):
                continue

            for row in table.find_all("tr")[1:]:
                record = self._parse_recharge_row(row)
                if record is not None:
                    records.append(record)

        return records

    def _parse_recharge_row(self, row: Tag) -> Optional[RechargeRecord]:
        """Parse one row of the recharge history table into a RechargeRecord."""
        cells = row.find_all("td")
        if len(cells) < 10:
            return None

        try:
            # Date is in whichever cell matches DD-Mon-YYYY format
            date_str = next(
                (c.get_text(strip=True) for c in cells
                 if re.match(r"\d{2}-\w{3}-\d{4}", c.get_text(strip=True))),
                "",
            )

            return RechargeRecord(
                seq_no=self._parse_int(cells[1].get_text(strip=True)),
                token=cells[2].get_text(strip=True),
                meter_rate=self._parse_float(cells[3].get_text(strip=True)),
                demand_charge=self._parse_float(cells[4].get_text(strip=True)),
                pfc_charge=self._parse_float(cells[5].get_text(strip=True)),
                vat=self._parse_float(cells[6].get_text(strip=True)),
                arrear=self._parse_float(cells[7].get_text(strip=True)),
                rebate=self._parse_float(cells[8].get_text(strip=True)),
                energy_amount=self._parse_float(cells[9].get_text(strip=True)),
                recharge_amount=self._parse_float(cells[10].get_text(strip=True)) if len(cells) > 10 else 0.0,
                energy_kwh=self._parse_float(cells[11].get_text(strip=True)) if len(cells) > 11 else 0.0,
                payment_method=cells[12].get_text(strip=True) if len(cells) > 12 else "N/A",
                recharge_date=self._parse_date(date_str),
                status=cells[-1].get_text(strip=True),
            )
        except (ValueError, IndexError):
            return None

    def _parse_monthly_usage_row(self, row: Tag) -> Optional[MonthlyUsage]:
        """Parse one row of the monthly usage table into a MonthlyUsage."""
        cells = row.find_all("td")
        if len(cells) < 12:
            return None

        try:
            return MonthlyUsage(
                year=self._parse_int(cells[0].get_text(strip=True)),
                month=cells[1].get_text(strip=True),
                total_recharge=self._parse_float(cells[2].get_text(strip=True)),
                rebate=self._parse_float(cells[3].get_text(strip=True)),
                energy_cost=self._parse_float(cells[4].get_text(strip=True)),
                meter_rent=self._parse_float(cells[5].get_text(strip=True)),
                demand_charge=self._parse_float(cells[6].get_text(strip=True)),
                pfc_charge=self._parse_float(cells[7].get_text(strip=True)),
                arrear=self._parse_float(cells[8].get_text(strip=True)),
                vat=self._parse_float(cells[9].get_text(strip=True)),
                total_deduction=self._parse_float(cells[10].get_text(strip=True)),
                end_balance=self._parse_float(cells[11].get_text(strip=True)),
                energy_kwh=self._parse_float(cells[12].get_text(strip=True)) if len(cells) > 12 else 0.0,
            )
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_float(text: str) -> float:
        """Extract the first decimal number from *text*, stripping non-numeric chars."""
        cleaned = re.sub(r"[^\d.\-]", "", text or "")
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_int(text: str) -> int:
        """Extract the first integer from *text*, stripping non-numeric chars."""
        cleaned = re.sub(r"[^\d]", "", text or "")
        return int(cleaned) if cleaned else 0

    @staticmethod
    def _parse_date(text: str) -> datetime:
        """Parse *text* into a datetime, trying several common portal formats."""
        formats = [
            "%d-%b-%Y %I:%M %p",
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text.strip(), fmt)
            except ValueError:
                continue
        return datetime.now()
