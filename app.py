import json
import os
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# On Render, set POS_DATA_FILE=/var/data/pos_data.json and attach a disk at /var/data.
DATA_FILE = Path(os.environ.get("POS_DATA_FILE", str(Path(__file__).with_name("pos_data.json"))))

DEFAULT_PRODUCTS = [
    {"product_code": "ZF1", "name": "Porksilog", "price": 8000, "stock": 18},
    {"product_code": "ZF2", "name": "Beef Tapa Bowl", "price": 9500, "stock": 12},
    {"product_code": "ZF3", "name": "Cheese Burger", "price": 6500, "stock": 16},
    {"product_code": "ZF4", "name": "French Fries", "price": 4500, "stock": 22},
    {"product_code": "ZF5", "name": "Chicken Siomai (4 pcs)", "price": 4000, "stock": 25},
    {"product_code": "ZF6", "name": "Iced Tea", "price": 2500, "stock": 40},
    {"product_code": "ZF7", "name": "Iced Coffee", "price": 5500, "stock": 24},
    {"product_code": "ZF8", "name": "Bottled Water", "price": 2000, "stock": 50},
    {"product_code": "ZF9", "name": "Leche Flan Cup", "price": 4000, "stock": 10},
    {"product_code": "ZF10", "name": "Pancit Canton", "price": 5500, "stock": 20},
]
DISCOUNTS = {"none": ("No Discount", 0), "senior": ("Senior Citizen", 20), "student": ("Student", 10)}


def money(cents):
    return f"₱{int(cents) // 100:,}.{int(cents) % 100:02d}"


def parse_money(value):
    try:
        amount = Decimal(str(value).strip().replace(",", "").replace("PHP", "").replace("₱", ""))
        if not amount.is_finite() or amount < 0:
            raise ValueError
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid nonnegative price, such as 125.50.") from None


def calculate_discount(subtotal, rate):
    return int((Decimal(subtotal) * Decimal(rate) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def default_data():
    return {"products": {p["product_code"]: dict(p) for p in DEFAULT_PRODUCTS}, "transactions": []}


def load_data():
    if not DATA_FILE.exists():
        data = default_data()
        save_data(data)
        return data
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(data.get("products"), dict) or not isinstance(data.get("transactions", []), list):
            raise ValueError("Unexpected data format.")
        data.setdefault("transactions", [])
        return data
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Unable to read data file {DATA_FILE}: {exc}") from exc


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = DATA_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_file.replace(DATA_FILE)


def get_products(data):
    return sorted(data["products"].values(), key=lambda p: p["product_code"])


def find_product(data, code):
    return data["products"].get(code.strip().upper())


def cart_details(data):
    cart = session.get("cart", {})
    lines, subtotal = [], 0
    for code, quantity in cart.items():
        product = find_product(data, code)
        if product and int(quantity) > 0:
            line_total = product["price"] * int(quantity)
            subtotal += line_total
            lines.append({"product": product, "quantity": int(quantity), "line_total": line_total})
    discount_key = session.get("discount", "none")
    label, rate = DISCOUNTS.get(discount_key, DISCOUNTS["none"])
    discount = calculate_discount(subtotal, rate)
    return lines, subtotal, discount, subtotal - discount, label, rate


@app.template_filter("money")
def money_filter(value):
    return money(value)


@app.route("/")
def index():
    data = load_data()
    query = request.args.get("q", "").strip().casefold()
    products = get_products(data)
    if query:
        products = [p for p in products if query in p["product_code"].casefold() or query in p["name"].casefold()]
    lines, subtotal, discount, total, discount_label, discount_rate = cart_details(data)
    return render_template(
        "index.html", products=products, all_products=get_products(data), query=request.args.get("q", ""),
        lines=lines, subtotal=subtotal, discount=discount, total=total,
        discount_label=discount_label, discount_rate=discount_rate,
        transactions=list(reversed(data["transactions"][-10:])), data_path=str(DATA_FILE)
    )


@app.post("/cart/add")
def add_to_cart():
    data = load_data()
    code = request.form.get("product_code", "").strip().upper()
    try:
        quantity = int(request.form.get("quantity", "1"))
        product = find_product(data, code)
        if not product:
            raise ValueError("Product code not found.")
        if quantity < 1:
            raise ValueError("Quantity must be at least 1.")
        cart = session.get("cart", {})
        new_quantity = int(cart.get(code, 0)) + quantity
        if new_quantity > int(product["stock"]):
            raise ValueError(f"Only {product['stock']} unit(s) of {product['name']} are in stock.")
        cart[code] = new_quantity
        session["cart"] = cart
        flash(f"Added {quantity} × {product['name']} to the cart.", "success")
    except (ValueError, TypeError) as exc:
        flash(str(exc) or "Enter a valid quantity.", "error")
    return redirect(url_for("index", q=request.form.get("return_q", "")))


@app.post("/cart/update")
def update_cart():
    data = load_data()
    code = request.form.get("product_code", "").strip().upper()
    try:
        quantity = int(request.form.get("quantity", "0"))
        cart = session.get("cart", {})
        product = find_product(data, code)
        if not product or code not in cart:
            raise ValueError("That item is not in your cart.")
        if quantity <= 0:
            cart.pop(code, None)
            flash("Item removed from cart.", "success")
        elif quantity > int(product["stock"]):
            raise ValueError(f"Only {product['stock']} unit(s) are in stock.")
        else:
            cart[code] = quantity
            flash("Cart quantity updated.", "success")
        session["cart"] = cart
    except (ValueError, TypeError) as exc:
        flash(str(exc) or "Enter a valid quantity.", "error")
    return redirect(url_for("index"))


@app.post("/cart/remove")
def remove_from_cart():
    cart = session.get("cart", {})
    cart.pop(request.form.get("product_code", "").strip().upper(), None)
    session["cart"] = cart
    flash("Item removed from cart.", "success")
    return redirect(url_for("index"))


@app.post("/cart/discount")
def set_discount():
    choice = request.form.get("discount", "none")
    if choice not in DISCOUNTS:
        choice = "none"
    session["discount"] = choice
    flash(f"Discount selected: {DISCOUNTS[choice][0]}.", "success")
    return redirect(url_for("index"))


@app.post("/checkout")
def checkout():
    data = load_data()
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for("index"))
    try:
        for code, quantity in cart.items():
            product = find_product(data, code)
            if not product or int(quantity) < 1:
                raise ValueError("Cart contains an invalid item.")
            if int(quantity) > int(product["stock"]):
                raise ValueError(f"Insufficient stock for {product['name']}. Available: {product['stock']}.")
        lines, subtotal, discount, total, discount_label, discount_rate = cart_details(data)
        payment = parse_money(request.form.get("payment", ""))
        if payment < total:
            raise ValueError(f"Insufficient payment. Amount due is {money(total)}.")
        now = datetime.now()
        transaction = {
            "transaction_id": now.strftime("T%Y%m%d%H%M%S%f"),
            "date": now.isoformat(timespec="seconds"),
            "items": [
                {"product_code": line["product"]["product_code"], "name": line["product"]["name"],
                 "unit_price": line["product"]["price"], "quantity": line["quantity"],
                 "subtotal": line["line_total"]}
                for line in lines
            ],
            "subtotal": subtotal, "discount": discount, "discount_label": discount_label,
            "discount_rate": discount_rate, "total": total, "payment": payment, "change": payment - total
        }
        for code, quantity in cart.items():
            data["products"][code]["stock"] -= int(quantity)
        data["transactions"].append(transaction)
        save_data(data)
        session["cart"] = {}
        session["discount"] = "none"
        session["last_receipt"] = transaction
        flash("Checkout completed. Stock has been deducted.", "success")
        return redirect(url_for("receipt", transaction_id=transaction["transaction_id"]))
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))


@app.route("/receipt/<transaction_id>")
def receipt(transaction_id):
    transaction = session.get("last_receipt")
    if not transaction or transaction.get("transaction_id") != transaction_id:
        data = load_data()
        transaction = next((t for t in data["transactions"] if t["transaction_id"] == transaction_id), None)
    if not transaction:
        flash("Receipt not found.", "error")
        return redirect(url_for("index"))
    return render_template("receipt.html", transaction=transaction)


@app.route("/admin")
def admin():
    data = load_data()
    query = request.args.get("q", "").strip().casefold()
    products = get_products(data)
    if query:
        products = [p for p in products if query in p["product_code"].casefold() or query in p["name"].casefold()]
    return render_template("admin.html", products=products, query=request.args.get("q", ""))


@app.post("/admin/product/add")
def add_product():
    data = load_data()
    try:
        code = request.form.get("product_code", "").strip().upper()
        name = request.form.get("name", "").strip()
        price = parse_money(request.form.get("price", ""))
        stock = int(request.form.get("stock", ""))
        if not code or code in data["products"]:
            raise ValueError("Product code must be nonempty and unique.")
        if not name:
            raise ValueError("Product name cannot be empty.")
        if price <= 0 or stock < 0:
            raise ValueError("Price must be above zero and stock cannot be negative.")
        data["products"][code] = {"product_code": code, "name": name, "price": price, "stock": stock}
        save_data(data)
        flash(f"{name} added.", "success")
    except (ValueError, TypeError) as exc:
        flash(str(exc) or "Check the product details.", "error")
    return redirect(url_for("admin"))


@app.post("/admin/product/edit")
def edit_product():
    data = load_data()
    code = request.form.get("product_code", "").strip().upper()
    product = find_product(data, code)
    try:
        if not product:
            raise ValueError("Product code not found.")
        name = request.form.get("name", "").strip()
        price = parse_money(request.form.get("price", ""))
        stock = int(request.form.get("stock", ""))
        if not name or price <= 0 or stock < 0:
            raise ValueError("Enter a name, a price above zero, and nonnegative stock.")
        product.update(name=name, price=price, stock=stock)
        save_data(data)
        flash(f"{code} updated.", "success")
    except (ValueError, TypeError) as exc:
        flash(str(exc) or "Check the product details.", "error")
    return redirect(url_for("admin"))


@app.post("/admin/product/delete")
def delete_product():
    data = load_data()
    code = request.form.get("product_code", "").strip().upper()
    if code in data["products"]:
        del data["products"][code]
        save_data(data)
        cart = session.get("cart", {})
        cart.pop(code, None)
        session["cart"] = cart
        flash(f"{code} deleted.", "success")
    else:
        flash("Product code not found.", "error")
    return redirect(url_for("admin"))


@app.post("/admin/product/stock")
def update_stock():
    data = load_data()
    code = request.form.get("product_code", "").strip().upper()
    try:
        product = find_product(data, code)
        if not product:
            raise ValueError("Product code not found.")
        quantity = int(request.form.get("quantity", ""))
        if quantity < 0:
            raise ValueError("Stock cannot be negative.")
        product["stock"] = quantity
        save_data(data)
        flash(f"Stock for {product['name']} set to {quantity}.", "success")
    except (ValueError, TypeError) as exc:
        flash(str(exc) or "Enter a whole-number stock quantity.", "error")
    return redirect(url_for("admin"))


@app.route("/reports")
def reports():
    data = load_data()
    transactions = list(reversed(data["transactions"]))
    item_count = sum(int(item["quantity"]) for t in data["transactions"] for item in t["items"])
    sales_total = sum(int(t["total"]) for t in data["transactions"])
    return render_template("reports.html", transactions=transactions, transaction_count=len(transactions),
                           item_count=item_count, sales_total=sales_total)


@app.post("/cart/clear")
def clear_cart():
    session["cart"] = {}
    session["discount"] = "none"
    flash("Cart cleared.", "success")
    return redirect(url_for("index"))


@app.errorhandler(500)
def server_error(error):
    app.logger.exception("Unexpected server error: %s", error)
    return "An unexpected server error occurred. Check the Render logs for details.", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
