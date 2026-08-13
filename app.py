#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TERY-EMBALLAGE — Vente en gros d'emballages (sacs et feuilles PP).
Flux : vitrine -> panier (plusieurs articles) -> commande (adresse de
livraison + méthode de paiement) -> confirmation.
- Prix par paliers selon la quantité (2 000 / 5 000 pièces et +).
- Livraison incluse 24 h à 48 h.
- Paiement : carte bancaire (terminal portable à la livraison), virement
  bancaire ou espèces (à la livraison) — même système que TeryParfum.
- Garantie : les produits défectueux peuvent être échangés.
Les montants sont toujours recalculés côté serveur.
"""
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tery_emballage.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PORT = int(os.environ.get("PORT", "8791"))

def load_secret_key():
    """Clé de session persistée (les logins admin survivent aux redémarrages)."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as fh:
                key = json.load(fh).get("secret_key")
                if key:
                    return key
        except Exception:
            pass
    key = secrets.token_hex(32)
    with open(CONFIG_PATH, "w") as fh:
        json.dump({"secret_key": key}, fh)
    return key


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or load_secret_key()

# ── Marque ──────────────────────────────────────────────────────────────
COMPANY = "Tery-Emballage"
COMPANY_EMAIL = "tery-emballage@tery.shop"
TAGLINE = "Vente en gros des emballages"
SHIPPING_DELAY = "Livraison incluse 24 h à 48 h"
WARRANTY = "Les produits défectueux peuvent être échangés."

MIN_QTY = 2000          # quantité minimale par produit (vente en gros)
MAX_QTY = 1_000_000     # plafond par produit

# Paliers de prix par pièce (du plus grand au plus petit)
TIERS = [
    (5000, 0.42),   # 5 000 pièces et +  -> 0,42 $ / pièce
    (2000, 0.50),   # 2 000 pièces et +  -> 0,50 $ / pièce
]
TIERS_DISPLAY = [  # ordre d'affichage (du plus accessible au meilleur prix)
    (2000, 0.50),
    (5000, 0.42),
]

PRODUCTS = {
    "sac-blanc": {
        "name": "Sac PP tissé blanc",
        "tagline": "Pour usage construction",
        "desc": (
            "Sac tissé en polypropylène (PP) blanc, non laminé, d'une "
            "dimension généreuse de 80 × 125 cm. Conçu pour l'usage "
            "construction : il supporte les matériaux lourds et les "
            "surfaces abrasives. Haut du sac coupé à chaud, bas en "
            "double pli avec couture simple."
        ),
        "image": "img/sac-blanc.webp",
        "gallery": ["img/sac-blanc.webp", "img/sac-blanc-2.webp", "img/sac-blanc-pile.webp"],
        "specs": [
            ("Dimensions", "80 × 125 cm"),
            ("Usage", "Construction"),
            ("Laminage", "Non laminé"),
            ("Poids du sac", "132 g"),
            ("Haut du sac", "Coupe à chaud (heat cut)"),
            ("Bas du sac", "Double pli, couture simple (double fold, single stitch)"),
        ],
    },
    "sac-transparent": {
        "name": "Sac PP tissé transparent",
        "tagline": "Pour chargement de chaussures",
        "desc": (
            "Sac tissé en polypropylène (PP) transparent, non laminé, "
            "de 80 × 115 cm. Pensé pour le chargement de chaussures : "
            "on identifie le contenu en un coup d'œil. Haut du sac "
            "coupé à chaud, bas en double pli avec couture simple."
        ),
        "image": "img/sac-transparent.webp",
        "gallery": ["img/sac-transparent.webp", "img/sac-transparent-usage.jpg", "img/sac-transparent-2.jpg"],
        "specs": [
            ("Dimensions", "80 × 115 cm"),
            ("Usage", "Chargement de chaussures"),
            ("Laminage", "Non laminé"),
            ("Poids du sac", "108 g"),
            ("Haut du sac", "Coupe à chaud (heat cut)"),
            ("Bas du sac", "Double pli, couture simple (double fold, single stitch)"),
        ],
    },
    "feuille-pp": {
        "name": "Feuille PP transparente",
        "tagline": "Pour balles de vêtements",
        "desc": (
            "Feuille de polypropylène (PP) transparente laminée de "
            "105 × 135 cm. Utilisée pour la mise en balles de vêtements "
            "(baling clothing) : elle protège les balles pendant le "
            "stockage et le transport. Poids de la feuille : 95 g."
        ),
        "image": "img/feuille-pp-1.jpg",
        "gallery": ["img/feuille-pp-1.jpg", "img/feuille-pp-2.jpg", "img/feuille-pp-3.jpg"],
        "specs": [
            ("Dimensions", "105 × 135 cm"),
            ("Usage", "Balles de vêtements (baling clothing)"),
            ("Laminage", "Laminée"),
            ("Poids de la feuille", "95 g"),
        ],
    },
}

BANK_DETAILS = {
    "beneficiaire": "Tery-Emballage Inc.",
    "banque": "Banque Nationale du Canada",
    "institution": "006",
    "transit": "00001",
    "compte": "6200-5678",
}

PAYMENT_METHODS = {
    "carte": {"label": "Carte de crédit", "sub": "Visa, Mastercard, American Express — terminal portable à la livraison"},
    "virement": {"label": "Virement bancaire", "sub": "Transfert bancaire — le plus utilisé"},
    "especes": {"label": "Espèces", "sub": "Payé en espèces à la livraison"},
}

PAYMENT_STATUS = {
    "carte": "Confirmée — paiement par carte à la livraison (terminal portable)",
    "virement": "En attente de réception du virement",
    "especes": "À régler à la livraison (espèces)",
}

STATUS_SHORT = {
    "carte": "Carte — à la livraison",
    "virement": "En attente du virement",
    "especes": "Espèces — à la livraison",
}

ADMIN_EMAIL = "admin@tery.shop"
ADMIN_PASSWORD = "admin123"


# ── Base de données ─────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                apartment TEXT DEFAULT '',
                city TEXT NOT NULL,
                province TEXT NOT NULL,
                postal_code TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                card_last4 TEXT DEFAULT '',
                subtotal REAL NOT NULL,
                shipping REAL NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_key TEXT NOT NULL,
                product_name TEXT NOT NULL,
                price REAL NOT NULL,
                qty INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'client'
            );
            """
        )
        # Compte admin initial (si aucun admin n'existe)
        row = db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()
        if row[0] == 0:
            db.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
                (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD), "Administrateur", "admin"),
            )


def next_ref():
    with sqlite3.connect(DB_PATH) as db:
        today = datetime.now().strftime("%Y%m%d")
        row = db.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE ref LIKE ?", (f"TE-{today}-%",)
        ).fetchone()
        return f"TE-{today}-{row[0] + 1:04d}"


# ── Helpers prix / panier / totaux ──────────────────────────────────────
def unit_price(qty):
    """Prix par pièce selon la quantité commandée (palier de gros)."""
    for min_qty, price in TIERS:
        if qty >= min_qty:
            return price
    return None  # sous la quantité minimale


def tier_label(qty):
    for min_qty, price in TIERS:
        if qty >= min_qty:
            return f"{min_qty:,}".replace(",", "\u202f") + " pièces et +"
    return ""


def cart_items():
    """Retourne les lignes du panier avec prix unitaire recalculé (palier)."""
    items = []
    cart = session.get("cart", {})
    for key, qty in cart.items():
        if key not in PRODUCTS or qty <= 0:
            continue
        price = unit_price(qty)
        if price is None:
            continue
        p = PRODUCTS[key]
        items.append({
            "key": key,
            "name": p["name"],
            "tagline": p["tagline"],
            "image": p["image"],
            "price": price,
            "qty": qty,
            "tier": tier_label(qty),
            "subtotal": round(price * qty, 2),
        })
    return items


def cart_count():
    return sum(q for q in session.get("cart", {}).values() if q > 0)


def cart_totals(items):
    subtotal = round(sum(i["subtotal"] for i in items), 2)
    return {"subtotal": subtotal, "shipping": 0.0, "total": round(subtotal, 2)}


@app.context_processor
def inject_globals():
    return {
        "COMPANY": COMPANY,
        "COMPANY_EMAIL": COMPANY_EMAIL,
        "TAGLINE": TAGLINE,
        "SHIPPING_DELAY": SHIPPING_DELAY,
        "WARRANTY": WARRANTY,
        "MIN_QTY": MIN_QTY,
        "TIERS_DISPLAY": TIERS_DISPLAY,
        "payment_methods": PAYMENT_METHODS,
        "STATUS_SHORT": STATUS_SHORT,
        "cart_count": cart_count(),
    }


@app.template_filter("money")
def money(value):
    return f"{value:,.2f} $".replace(",", "\u202f").replace(".", ",")


@app.template_filter("intdot")
def intdot(value):
    return f"{value:,}".replace(",", "\u202f")


# ── Pages ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS)


@app.route("/produit/<key>")
def product_page(key):
    if key not in PRODUCTS:
        return redirect(url_for("index"))
    return render_template("produit.html", pkey=key, p=PRODUCTS[key])


@app.route("/panier")
def cart_page():
    items = cart_items()
    totals = cart_totals(items)
    return render_template("panier.html", items=items, totals=totals)


def is_ajax():
    return request.headers.get("X-Requested-With") == "fetch"


@app.route("/panier/ajouter", methods=["POST"])
def cart_add():
    key = request.form.get("product", "")
    try:
        qty = int(request.form.get("qty", 0))
    except ValueError:
        qty = 0
    if key not in PRODUCTS:
        return redirect(url_for("index"))
    qty = max(0, min(qty, MAX_QTY))
    if qty < MIN_QTY:
        msg = (
            f"Quantité minimale : {MIN_QTY:,} pièces par produit "
            "(vente en gros).".replace(",", "\u202f")
        )
        if is_ajax():
            return jsonify({"ok": False, "error": msg}), 400
        from flask import flash
        flash(msg, "error")
        return redirect(url_for("product_page", key=key))
    cart = session.get("cart", {})
    cart[key] = min(cart.get(key, 0) + qty, MAX_QTY)
    session["cart"] = cart
    if is_ajax():
        return jsonify({"ok": True, "count": cart_count(), "qty": qty})
    return redirect(url_for("cart_page"))


@app.route("/panier/modifier", methods=["POST"])
def cart_update():
    key = request.form.get("product", "")
    try:
        qty = int(request.form.get("qty", 0))
    except ValueError:
        qty = 0
    cart = session.get("cart", {})
    if key not in cart or key not in PRODUCTS:
        return redirect(url_for("cart_page"))
    if qty <= 0:
        cart.pop(key, None)
    else:
        qty = min(qty, MAX_QTY)
        if qty < MIN_QTY:
            from flask import flash
            flash(
                f"Quantité minimale : {MIN_QTY:,} pièces par produit. Votre quantité est inchangée.".replace(",", "\u202f"),
                "error",
            )
            return redirect(url_for("cart_page"))
        cart[key] = qty
    session["cart"] = cart
    return redirect(url_for("cart_page"))


@app.route("/panier/retirer", methods=["POST"])
def cart_remove():
    key = request.form.get("product", "")
    cart = session.get("cart", {})
    cart.pop(key, None)
    session["cart"] = cart
    return redirect(url_for("cart_page"))


@app.route("/commande")
def checkout():
    items = cart_items()
    if not items:
        return redirect(url_for("cart_page"))
    totals = cart_totals(items)
    return render_template(
        "commande.html", items=items, totals=totals, bank_details=BANK_DETAILS
    )


POSTAL_RE = re.compile(r"^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[+()\-.\s\d]{7,20}$")
CARD_RE = re.compile(r"^\d{13,19}$")


def luhn_ok(number):
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@app.route("/commande", methods=["POST"])
def checkout_submit():
    items = cart_items()
    if not items:
        return redirect(url_for("cart_page"))
    totals = cart_totals(items)

    f = request.form
    errors = []
    def req(name, label):
        val = (f.get(name) or "").strip()
        if not val:
            errors.append(f"Le champ « {label} » est requis.")
        return val

    first_name = req("first_name", "Prénom")
    last_name = req("last_name", "Nom")
    email = req("email", "Courriel")
    phone = req("phone", "Téléphone")
    address = req("address", "Adresse")
    city = req("city", "Ville")
    province = req("province", "Province")
    postal = req("postal_code", "Code postal")
    apartment = (f.get("apartment") or "").strip()
    method = f.get("payment_method", "")

    if email and not EMAIL_RE.match(email):
        errors.append("Le courriel n'est pas valide.")
    if phone and not PHONE_RE.match(phone):
        errors.append("Le numéro de téléphone n'est pas valide.")
    if postal and not POSTAL_RE.match(postal):
        errors.append("Le code postal doit respecter le format canadien (ex. H2X 1Y4).")

    if method not in PAYMENT_METHODS:
        errors.append("Veuillez choisir une méthode de paiement.")

    card_last4 = ""
    if method == "carte":
        card_name = (f.get("card_name") or "").strip()
        card_number = (f.get("card_number") or "").replace(" ", "").replace("-", "")
        card_expiry = (f.get("card_expiry") or "").strip()
        card_cvc = (f.get("card_cvc") or "").strip()
        if not card_name:
            errors.append("Veuillez indiquer le nom du titulaire de la carte.")
        if not CARD_RE.match(card_number) or not luhn_ok(card_number):
            errors.append("Le numéro de carte est invalide.")
        m = re.match(r"^(\d{2})/(\d{2})$", card_expiry)
        if not m:
            errors.append("La date d'expiration doit être au format MM/AA.")
        else:
            mm, yy = int(m.group(1)), 2000 + int(m.group(2))
            if not (1 <= mm <= 12) or (yy, mm) < (datetime.now().year, datetime.now().month):
                errors.append("La date d'expiration de la carte est dépassée.")
        if not re.match(r"^\d{3,4}$", card_cvc):
            errors.append("Le code de sécurité (CVC) doit contenir 3 ou 4 chiffres.")
        card_last4 = card_number[-4:]

    if errors:
        return render_template(
            "commande.html", items=items, totals=totals,
            bank_details=BANK_DETAILS, errors=errors, form=f,
        ), 400

    status = PAYMENT_STATUS[method]
    ref = next_ref()
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            """INSERT INTO orders
               (ref, first_name, last_name, email, phone, address, apartment,
                city, province, postal_code, payment_method, card_last4,
                subtotal, shipping, total, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ref, first_name, last_name, email, phone, address, apartment,
             city, province, postal, method, card_last4,
             totals["subtotal"], totals["shipping"], totals["total"], status, created),
        )
        order_id = cur.lastrowid
        for i in items:
            db.execute(
                """INSERT INTO order_items
                   (order_id, product_key, product_name, price, qty)
                   VALUES (?,?,?,?,?)""",
                (order_id, i["key"], i["name"], i["price"], i["qty"]),
            )
    session["cart"] = {}
    return redirect(url_for("confirmation", ref=ref))


@app.route("/confirmation/<ref>")
def confirmation(ref):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE ref = ?", (ref,)).fetchone()
    if order is None:
        return redirect(url_for("index"))
    order_items = db.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order["id"],)
    ).fetchall()
    bank_details = BANK_DETAILS if order["payment_method"] == "virement" else None
    return render_template(
        "confirmation.html", order=order, order_items=order_items,
        bank_details=bank_details,
        payment_label=PAYMENT_METHODS[order["payment_method"]]["label"],
    )


# ── Administration ──────────────────────────────────────────────────────
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            session.clear()
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            session.clear()
            return redirect(url_for("admin_login", next=request.path))
        if user["role"] != "admin":
            session.clear()
            return redirect(url_for("admin_login", next=request.path, error="admin_required"))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user() is not None:
        return redirect(url_for("admin_dashboard"))
    nxt = request.args.get("next") or url_for("admin_dashboard")
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template(
                "admin_login.html", error="Courriel ou mot de passe incorrect.",
                next=nxt, form=request.form,
            ), 401
        session["user_id"] = user["id"]
        if nxt and nxt != url_for("admin_logout"):
            return redirect(nxt)
        return redirect(url_for("admin_dashboard"))
    error = "Cette zone est réservée aux administrateurs." if request.args.get("error") else None
    return render_template("admin_login.html", next=nxt, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    orders = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    data = []
    for o in orders:
        d = dict(o)
        d["items"] = [
            dict(i) for i in db.execute(
                "SELECT * FROM order_items WHERE order_id = ?", (o["id"],)
            ).fetchall()
        ]
        data.append(d)
    return render_template(
        "admin.html", orders=orders, orders_json=json.dumps(data, ensure_ascii=False),
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT, debug=True)
