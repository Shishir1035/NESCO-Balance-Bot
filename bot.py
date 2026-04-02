"""Telegram bot command handlers."""
import logging
from collections.abc import Callable
from typing import Any, Optional

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import Config
from nesco_client import NescoClient

logger = logging.getLogger(__name__)

_WELCOME = """🔋 *NESCO Prepaid Balance Bot*

Check your electricity balance instantly!

*Commands:*
/check `<consumer_no>` — Balance & customer info
/history `<consumer_no>` — Last 5 recharges
/usage `<consumer_no>` — 6-month usage report
/help — Show this message

*Quick lookup:* just send the consumer number

*Example:*
`/check 77900157`

⚡ Powered by NESCO Customer Portal"""


class NescoBot:
    """Telegram bot that wraps NescoClient for user-facing command handling."""

    def __init__(self, config: Config, client: NescoClient) -> None:
        self.config = config
        self.client = client
        self._app: Optional[Application] = None

    # ------------------------------------------------------------------ #
    # Command handlers                                                     #
    # ------------------------------------------------------------------ #

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start and /help — show the welcome message."""
        await update.message.reply_text(_WELCOME, parse_mode=ParseMode.MARKDOWN)

    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /check <consumer_no> — show balance and customer info."""
        consumer_no = await self._parse_consumer_no(update, context, "/check")
        if consumer_no:
            await self._run_lookup(
                update,
                consumer_no,
                loading_text="🔍 Fetching data...",
                fetch_fn=self.client.get_customer_info,
                format_fn=lambda r: r.format_telegram(),
            )

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /history <consumer_no> — show last 5 recharge transactions."""
        consumer_no = await self._parse_consumer_no(update, context, "/history")
        if consumer_no:
            await self._run_lookup(
                update,
                consumer_no,
                loading_text="🔍 Fetching history...",
                fetch_fn=self.client.get_customer_info,
                format_fn=lambda r: r.format_history(limit=5),
            )

    async def usage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /usage <consumer_no> — show 6-month usage report."""
        consumer_no = await self._parse_consumer_no(update, context, "/usage")
        if consumer_no:
            await self._run_lookup(
                update,
                consumer_no,
                loading_text="🔍 Fetching monthly usage...",
                fetch_fn=self.client.get_monthly_usage,
                format_fn=lambda r: r.format_telegram(limit=6),
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle plain-text messages — treat a bare number as a quick /check."""
        text = update.message.text.strip()
        if text.isdigit() and len(text) >= 6:
            await self._run_lookup(
                update,
                text,
                loading_text="🔍 Fetching data...",
                fetch_fn=self.client.get_customer_info,
                format_fn=lambda r: r.format_telegram(),
            )
        else:
            await update.message.reply_text(
                "💡 Send a consumer number directly, or use /check"
            )

    # ------------------------------------------------------------------ #
    # Bot lifecycle                                                        #
    # ------------------------------------------------------------------ #

    def build(self) -> Application:
        """Construct and return the configured Application."""
        builder = Application.builder().token(self.config.telegram_token)

        if self.config.proxy_url:
            from telegram.request import HTTPXRequest
            builder = builder.request(HTTPXRequest(proxy=self.config.proxy_url))

        app = builder.build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.start))
        app.add_handler(CommandHandler("check", self.check))
        app.add_handler(CommandHandler("history", self.history))
        app.add_handler(CommandHandler("usage", self.usage))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        self._app = app
        return app

    def run(self) -> None:
        """Build the application and start polling (blocking)."""
        logger.info("Starting NESCO Bot")
        self.build().run_polling(allowed_updates=Update.ALL_TYPES)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _parse_consumer_no(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        command: str,
    ) -> Optional[str]:
        """Validate command arguments and return the consumer number.

        Sends an error reply and returns None if validation fails.
        """
        if not context.args:
            await update.message.reply_text(
                f"⚠️ Please provide a consumer number\nExample: `{command} 77900157`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return None

        consumer_no = context.args[0].strip()
        if not consumer_no.isdigit():
            await update.message.reply_text("❌ Consumer number must be numeric.")
            return None

        return consumer_no

    @staticmethod
    async def _run_lookup(
        update: Update,
        consumer_no: str,
        *,
        loading_text: str,
        fetch_fn: Callable[[str], Any],
        format_fn: Callable[[Any], str],
    ) -> None:
        """Show a loading message, call *fetch_fn*, then edit the message with the result."""
        loading_msg: Message = await update.message.reply_text(loading_text)

        try:
            result = fetch_fn(consumer_no)
            if result:
                await loading_msg.edit_text(format_fn(result), parse_mode=ParseMode.MARKDOWN)
            else:
                await loading_msg.edit_text(
                    f"❌ No data found for consumer `{consumer_no}`.\n"
                    "Please verify the number and try again.",
                    parse_mode=ParseMode.MARKDOWN,
                )
        except Exception:
            logger.exception("Lookup failed for consumer %s", consumer_no)
            await loading_msg.edit_text("❌ Failed to fetch data. Please try again later.")
