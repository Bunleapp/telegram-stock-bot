import logging
import os
from datetime import datetime
import json
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from google.oauth2.service_account import Credentials

# Load the JSON string from the environment variable
creds_json = os.environ.get('GOOGLE_CREDS_JSON')

if creds_json:
    # Running on Render: Parse the JSON string into a dictionary
    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )
else:
    # Running locally: load from the file
    credentials = Credentials.from_service_account_file(
        "credentials/service_account.json",
        scopes=SCOPES
    )
# =========================
# LOAD ENV VARIABLES
# =========================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
ALLOWED_USERS = os.getenv("ALLOWED_USERS")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing in .env")

if not SPREADSHEET_URL:
    raise ValueError("SPREADSHEET_URL missing in .env")

if not ALLOWED_USERS:
    raise ValueError("ALLOWED_USERS missing in .env")

# Convert IDs into list
ALLOWED_USERS = list(map(int, ALLOWED_USERS.split(",")))

# =========================
# SETTINGS
# =========================

LOW_STOCK_LIMIT = 5

# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# =========================
# GOOGLE SHEETS CONNECTION
# =========================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Load the JSON string from the environment variable
creds_json = os.environ.get('GOOGLE_CREDS_JSON')

if creds_json:
    # Running on Render: Parse the JSON string into a dictionary
    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )
else:
    # Running locally: load from the file
    credentials = Credentials.from_service_account_file(
        "credentials/service_account.json",
        scopes=SCOPES
    )

client = gspread.authorize(credentials)

spreadsheet = client.open_by_url(SPREADSHEET_URL)
# =========================
# CREATE / LOAD WORKSHEETS
# =========================

try:
    inventory_sheet = spreadsheet.worksheet("Inventory")
except:
    inventory_sheet = spreadsheet.add_worksheet(
        title="Inventory",
        rows=1000,
        cols=10
    )

try:
    sales_sheet = spreadsheet.worksheet("Sales")
except:
    sales_sheet = spreadsheet.add_worksheet(
        title="Sales",
        rows=1000,
        cols=10
    )

# =========================
# CREATE HEADERS IF EMPTY
# =========================

if not inventory_sheet.get_all_values():

    inventory_sheet.append_row([
        "Product ID",
        "Product Name",
        "Quantity",
        "Price",
        "Last Updated"
    ])

if not sales_sheet.get_all_values():

    sales_sheet.append_row([
        "Product ID",
        "Product Name",
        "Quantity Sold",
        "Price",
        "Date"
    ])

# =========================
# MENU KEYBOARD
# =========================

keyboard = [
    ["📦 View Stock", "➕ Add Stock"],
    ["💸 Sell Product", "📈 View Sales"],
    ["🔍 Check Product", "⚠️ Low Stock"],
    ["❓ Help"]
]

reply_markup = ReplyKeyboardMarkup(
    keyboard,
    resize_keyboard=True
)

# =========================
# AUTHORIZATION
# =========================


def is_authorized(user_id):
    return user_id in ALLOWED_USERS


async def check_auth(update: Update):

    if not is_authorized(update.effective_user.id):

        await update.message.reply_text(
            "❌ Unauthorized User"
        )

        return False

    return True

# =========================
# HELPER FUNCTION
# =========================


def find_product(product_name):

    records = inventory_sheet.get_all_records()

    for index, record in enumerate(records, start=2):

        if record["Product Name"].lower() == product_name.lower():

            return index, record

    return None, None

# =========================
# START COMMAND
# =========================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    await update.message.reply_text(
        "📦 Welcome to Stock Management Bot",
        reply_markup=reply_markup
    )

# =========================
# HELP COMMAND
# =========================


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    help_text = """
📋 AVAILABLE COMMANDS

/addstock product_name quantity price
Example:
/addstock Mouse 10 15

/sell product_name quantity
Example:
/sell Mouse 2

/viewstock
/viewsales
/check product_name
/lowstock
"""

    await update.message.reply_text(help_text)

# =========================
# ADD STOCK
# =========================


async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    try:

        args = context.args

        if len(args) < 3:

            await update.message.reply_text(
                "❌ Usage:\n/addstock product_name quantity price"
            )

            return

        quantity = args[-2]
        price = args[-1]
        product_name = " ".join(args[:-2])

        quantity = int(quantity)
        price = float(price)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row_index, product = find_product(product_name)

        # EXISTING PRODUCT
        if product:

            new_quantity = int(product["Quantity"]) + quantity

            inventory_sheet.update_cell(row_index, 3, new_quantity)
            inventory_sheet.update_cell(row_index, 4, price)
            inventory_sheet.update_cell(row_index, 5, timestamp)

            await update.message.reply_text(
                f"✅ Stock Updated\n\n"
                f"Product: {product_name}\n"
                f"Added: {quantity}\n"
                f"New Quantity: {new_quantity}"
            )

        # NEW PRODUCT
        else:

            product_id = f"P{len(inventory_sheet.get_all_records()) + 1}"

            inventory_sheet.append_row([
                product_id,
                product_name,
                quantity,
                price,
                timestamp
            ])

            await update.message.reply_text(
                f"✅ New Product Added\n\n"
                f"Product: {product_name}\n"
                f"Quantity: {quantity}\n"
                f"Price: ${price}"
            )

    except Exception as e:

        logger.exception("Add stock error")

        await update.message.reply_text(
            f"❌ Error: {e}"
        )

# =========================
# SELL PRODUCT
# =========================


async def sell_product(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    try:

        args = context.args

        if len(args) != 2:

            await update.message.reply_text(
                "❌ Usage:\n/sell product_name quantity"
            )

            return

        product_name, quantity = args

        quantity = int(quantity)

        row_index, product = find_product(product_name)

        if not product:

            await update.message.reply_text(
                "❌ Product not found."
            )

            return

        current_stock = int(product["Quantity"])

        if quantity > current_stock:

            await update.message.reply_text(
                f"❌ Insufficient stock.\nAvailable: {current_stock}"
            )

            return

        new_stock = current_stock - quantity

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        inventory_sheet.update_cell(row_index, 3, new_stock)
        inventory_sheet.update_cell(row_index, 5, timestamp)

        sales_sheet.append_row([
            product["Product ID"],
            product_name,
            quantity,
            product["Price"],
            timestamp
        ])

        message = (
            f"✅ Product Sold\n\n"
            f"Product: {product_name}\n"
            f"Sold: {quantity}\n"
            f"Remaining: {new_stock}"
        )

        if new_stock <= LOW_STOCK_LIMIT:

            message += "\n\n⚠️ LOW STOCK ALERT"

        await update.message.reply_text(message)

    except Exception as e:

        logger.exception("Sell product error")

        await update.message.reply_text(
            f"❌ Error: {e}"
        )

# =========================
# VIEW STOCK
# =========================


async def view_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    try:

        records = inventory_sheet.get_all_records()

        if not records:

            await update.message.reply_text(
                "📦 No inventory found."
            )

            return

        response = "📦 CURRENT INVENTORY\n\n"

        for record in records:

            response += (
                f"ID: {record['Product ID']}\n"
                f"Product: {record['Product Name']}\n"
                f"Quantity: {record['Quantity']}\n"
                f"Price: ${record['Price']}\n"
                f"-------------------\n"
            )

        await update.message.reply_text(response)

    except Exception as e:

        logger.exception("View stock error")

        await update.message.reply_text(
            f"❌ Error: {e}"
        )

# =========================
# VIEW SALES
# =========================


async def view_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    try:

        records = sales_sheet.get_all_records()

        if not records:

            await update.message.reply_text(
                "📈 No sales found."
            )

            return

        response = "📈 SALES HISTORY\n\n"

        for record in records[-10:]:

            response += (
                f"Product: {record['Product Name']}\n"
                f"Sold: {record['Quantity Sold']}\n"
                f"Price: ${record['Price']}\n"
                f"Date: {record['Date']}\n"
                f"-------------------\n"
            )

        await update.message.reply_text(response)

    except Exception as e:

        logger.exception("View sales error")

        await update.message.reply_text(
            f"❌ Error: {e}"
        )

# =========================
# CHECK PRODUCT
# =========================


async def check_product(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    try:

        args = context.args

        if len(args) != 1:

            await update.message.reply_text(
                "❌ Usage:\n/check product_name"
            )

            return

        product_name = args[0]

        row_index, product = find_product(product_name)

        if not product:

            await update.message.reply_text(
                "❌ Product not found."
            )

            return

        await update.message.reply_text(
            f"🔍 PRODUCT DETAILS\n\n"
            f"ID: {product['Product ID']}\n"
            f"Product: {product['Product Name']}\n"
            f"Quantity: {product['Quantity']}\n"
            f"Price: ${product['Price']}"
        )

    except Exception as e:

        logger.exception("Check product error")

        await update.message.reply_text(
            f"❌ Error: {e}"
        )

# =========================
# LOW STOCK
# =========================


async def low_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await check_auth(update):
        return

    try:

        records = inventory_sheet.get_all_records()

        low_stock_items = []

        for record in records:

            if int(record["Quantity"]) <= LOW_STOCK_LIMIT:

                low_stock_items.append(record)

        if not low_stock_items:

            await update.message.reply_text(
                "✅ No low stock products."
            )

            return

        response = "⚠️ LOW STOCK PRODUCTS\n\n"

        for item in low_stock_items:

            response += (
                f"{item['Product Name']} "
                f"({item['Quantity']} left)\n"
            )

        await update.message.reply_text(response)

    except Exception as e:

        logger.exception("Low stock error")

        await update.message.reply_text(
            f"❌ Error: {e}"
        )

# =========================
# BUTTON HANDLER
# =========================


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "📦 View Stock":
        await view_stock(update, context)

    elif text == "➕ Add Stock":
        await update.message.reply_text(
            "Use:\n/addstock product_name quantity price"
        )

    elif text == "💸 Sell Product":
        await update.message.reply_text(
            "Use:\n/sell product_name quantity"
        )

    elif text == "📈 View Sales":
        await view_sales(update, context)

    elif text == "🔍 Check Product":
        await update.message.reply_text(
            "Use:\n/check product_name"
        )

    elif text == "⚠️ Low Stock":
        await low_stock(update, context)

    elif text == "❓ Help":
        await help_command(update, context)

# =========================
# UNKNOWN COMMAND
# =========================


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "❌ Unknown command.\nUse /help"
    )

# =========================
# MAIN FUNCTION
# =========================


def main():

    app = Application.builder().token(TOKEN).build()

    # COMMANDS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addstock", add_stock))
    app.add_handler(CommandHandler("sell", sell_product))
    app.add_handler(CommandHandler("viewstock", view_stock))
    app.add_handler(CommandHandler("viewsales", view_sales))
    app.add_handler(CommandHandler("check", check_product))
    app.add_handler(CommandHandler("lowstock", low_stock))

    # BUTTON HANDLER
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    # UNKNOWN COMMAND
    app.add_handler(
        MessageHandler(filters.COMMAND, unknown)
    )

    print("✅ Bot is running...")

    app.run_polling()

# =========================
# START BOT
# =========================


if __name__ == "__main__":
    main()
