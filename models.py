"""Data models for NESCO customer information."""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class MonthlyUsage:
    """One month of electricity usage."""

    year: int
    month: str
    total_recharge: float
    rebate: float
    energy_cost: float
    meter_rent: float
    demand_charge: float
    pfc_charge: float
    arrear: float
    vat: float
    total_deduction: float
    end_balance: float
    energy_kwh: float


@dataclass
class RechargeRecord:
    """A single recharge transaction."""

    seq_no: int
    token: str
    meter_rate: float
    demand_charge: float
    pfc_charge: float
    vat: float
    arrear: float
    rebate: float
    energy_amount: float
    recharge_amount: float
    energy_kwh: float
    payment_method: str
    recharge_date: datetime
    status: str


@dataclass
class CustomerInfo:
    """NESCO prepaid customer details and current balance."""

    customer_name: str
    address: str
    mobile: str
    office: str
    feeder: str
    consumer_no: str
    meter_no: str
    sanctioned_load: float
    tariff: str
    meter_type: str
    meter_status: str
    installation_date: str
    min_recharge: float
    balance: float
    balance_updated_at: str
    recharge_history: List[RechargeRecord]
    father_name: Optional[str] = None

    def format_telegram(self) -> str:
        """Format as a Telegram Markdown message."""
        balance_indicator = "🔴" if self.balance < self.min_recharge else "🟢"

        lines = [
            "🔋 *NESCO Prepaid Balance*",
            "",
            f"👤 {self.customer_name}",
            f"📍 {self.address}",
            "",
            "┌─────────────────────",
            f"│ 🔌 Meter: `{self.meter_no}`",
            f"│ 📊 Consumer: `{self.consumer_no}`",
            f"│ ⚡ Load: {self.sanctioned_load} kW ({self.tariff})",
            f"│ 📶 Status: {self.meter_status}",
            "└─────────────────────",
            "",
            f"{balance_indicator} *Balance: ৳{self.balance:.2f}*",
            f"🕐 Updated: {self.balance_updated_at}",
        ]

        if self.recharge_history:
            last = self.recharge_history[0]
            lines += [
                "",
                "📅 *Last Recharge:*",
                f"   ৳{last.recharge_amount:.0f} via {last.payment_method}",
                f"   {last.recharge_date.strftime('%d-%b-%Y %I:%M %p')}",
            ]

        return "\n".join(lines)

    def format_history(self, limit: int = 5) -> str:
        """Format recharge history as a Telegram Markdown message."""
        if not self.recharge_history:
            return "📭 No recharge history found."

        lines = [f"📜 *Recharge History* (Consumer: `{self.consumer_no}`)", ""]

        for i, record in enumerate(self.recharge_history[:limit], start=1):
            status_icon = "✅" if "success" in record.status.lower() else "❌"
            lines.append(
                f"{i}. {status_icon} ৳{record.recharge_amount:.0f} | {record.payment_method}"
            )
            lines.append(
                f"   📅 {record.recharge_date.strftime('%d-%b-%Y')} | ⚡ {record.energy_kwh:.2f} kWh"
            )
            lines.append("")

        return "\n".join(lines).strip()


@dataclass
class MonthlyUsageReport:
    """Monthly usage report for a customer."""

    consumer_no: str
    records: List[MonthlyUsage]

    def format_telegram(self, limit: int = 6) -> str:
        """Format monthly usage as a Telegram Markdown message."""
        if not self.records:
            return "📭 No monthly usage data found."

        shown = self.records[:limit]
        total_kwh = sum(r.energy_kwh for r in shown)
        total_recharge = sum(r.total_recharge for r in shown)

        lines = [
            "📊 *Monthly Usage Report*",
            f"Consumer: `{self.consumer_no}`",
            "",
        ]

        for record in shown:
            lines += [
                f"📅 *{record.month} {record.year}*",
                f"   💰 Recharged: ৳{record.total_recharge:,.0f}",
                f"   ⚡ Used: {record.energy_kwh:.1f} kWh (৳{record.energy_cost:.0f})",
                f"   📉 End Balance: ৳{record.end_balance:.2f}",
                "",
            ]

        lines += [
            "─────────────────",
            f"📈 *{limit}-Month Summary:*",
            f"   Total Recharged: ৳{total_recharge:,.0f}",
            f"   Total Used: {total_kwh:.1f} kWh",
        ]

        return "\n".join(lines)
