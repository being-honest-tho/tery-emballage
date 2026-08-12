#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit E2E Tery-Emballage — vente en gros, parcours boutique complet.
Paliers : 2 000+ = 0,50 $, 5 000+ = 0,42 $ / pièce.
Livraison incluse 24 h à 48 h. Paiement : carte (à la livraison),
virement, espèces. Usage : python3 check_teryemballage.py"""
import os
import re
import sqlite3
import uuid

from playwright.sync_api import sync_playwright

BASE = "/home/robii/tery-emballage"
DB = os.path.join(BASE, "tery_emballage.db")
URL = "http://127.0.0.1:8791"
SHOT = os.path.join(BASE, "audit2")
os.makedirs(SHOT, exist_ok=True)

EMAIL = f"test-te-{uuid.uuid4().hex[:8]}@example.com"
PASS_LINES, FAIL_LINES = [], []
BASE_ORDERS = 0


def norm(s):
    """Normalise espaces insécables → espace simple pour les comparaisons."""
    return (s or "").replace("\u202f", " ").replace("\u00a0", " ")


def check(name, ok, detail=""):
    (PASS_LINES if ok else FAIL_LINES).append(f"{name}: {detail if not ok else 'OK'}")
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if not ok else ""))


def db_orders():
    with sqlite3.connect(DB) as c:
        return c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]


def fill_co(page, method, postal="H2X 1Y4"):
    """Remplit le formulaire de commande et choisit la méthode."""
    page.fill("#first_name", "Test")
    page.fill("#last_name", "Emballage")
    page.fill("#email", EMAIL)
    page.fill("#phone", "514 555-0199")
    page.fill("#address", "1234, rue de la Montagne")
    page.fill("#city", "Montréal")
    page.select_option("#province", "Québec")
    page.fill("#postal_code", postal)
    page.check(f"input[name='payment_method'][value='{method}']", force=True)
    if method == "carte":
        page.fill("#card_name", "Test Emballage")
        page.fill("#card_number", "4242 4242 4242 4242")
        page.fill("#card_expiry", "12/30")
        page.fill("#card_cvc", "123")


def add_product(page, key, qty, wait=True):
    """Depuis la page produit : fixe la quantité et ajoute au panier (AJAX)."""
    page.fill(".buy-qty .qty-input", str(qty))
    page.locator(".js-add-cart button[type=submit]").click()
    if wait:
        page.wait_for_timeout(900)


def main():
    global BASE_ORDERS
    BASE_ORDERS = db_orders()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
                                    executable_path="/home/robii/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
                                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])

        # ═══════════ DESKTOP 1440x900 ═══════════
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)

        # ── Accueil ──
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        body = norm(page.inner_text("body"))
        check("accueil: titre", "Tery-Emballage" in page.title() and "Vente en gros des emballages" in page.title())
        check("accueil: tagline gros", "Vente en gros des emballages" in body)
        check("accueil: 3 produits",
              all(x in body for x in ["Sac PP tissé blanc", "Sac PP tissé transparent", "Feuille PP transparente"]))
        check("accueil: paliers 0,50 / 0,42",
              all(x in body for x in ["0,50", "0,42"])
              and body.upper().count("PIÈCES ET +") >= 2)
        check("accueil: plus de palier 0,40", "0,40" not in body)
        check("accueil: meilleur prix flag", "MEILLEUR PRIX" in body.upper())
        check("accueil: livraison incluse 24-48h", "Livraison incluse 24 h à 48 h" in body)
        check("accueil: garantie défectueux échangés", "Les produits défectueux peuvent être échangés" in body)
        check("accueil: email contact", "tery-emballage@tery.shop" in body)
        check("accueil: 3 paiements",
              all(x in body for x in ["Carte de crédit", "Virement bancaire", "Espèces"]))
        check("accueil: dès 2 000 pièces", "DÈS 2 000 PIÈCES" in body.upper())
        check("accueil: images chargées",
              page.evaluate("[...document.images].every(i => i.complete && i.naturalWidth > 0)"))
        check("accueil: hero carrousel 3 produits",
              page.locator(".hero-carousel .carousel-slide").count() == 3)
        check("accueil: cartes = produit + usage (switch)",
              page.locator(".product-card .card-carousel").count() == 3
              and page.locator(".card-carousel .carousel-slide").count() == 6)
        check("accueil: pas de débordement horizontal",
              page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        page.screenshot(path=os.path.join(SHOT, "01-accueil.png"))

        # ── Page produit sac-blanc ──
        page.goto(URL + "/produit/sac-blanc", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        pbody = norm(page.inner_text("body"))
        check("produit: specs complètes",
              all(x in pbody for x in ["80 × 125 cm", "132 g", "Coupe à chaud (heat cut)",
                                       "Double pli, couture simple (double fold, single stitch)",
                                       "Non laminé", "Construction"]))
        check("produit: quantité min 2000",
              page.locator(".buy-qty .qty-input").input_value() == "2000")
        check("produit: paliers affichés",
              all(x in pbody for x in ["0,50", "0,42"]) and "pièces et +" in pbody)
        page.locator(".buy-qty .qty-btn[data-step='100']").click()
        page.wait_for_timeout(300)
        check("produit: stepper +100 → 2100",
              page.locator(".buy-qty .qty-input").input_value() == "2100")
        page.locator(".buy-qty .qty-btn[data-step='-100']").click()
        page.wait_for_timeout(300)
        check("produit: stepper −100 → 2000 (min)",
              page.locator(".buy-qty .qty-input").input_value() == "2000")

        # ── Ajout AJAX : 2000 pièces ──
        add_product(page, "sac-blanc", 2000)
        page.wait_for_function(
            "() => { const el = document.querySelector('.cart-count'); "
            "return el && parseInt(el.textContent.replace(/\\D/g, ''), 10) === 2000; }",
            timeout=6000)
        check("ajout: badge = 2 000",
              norm(page.locator(".cart-count").inner_text()).strip() == "2 000")

        # ── Ajout sous le minimum : erreur locale, badge inchangé ──
        add_product(page, "sac-blanc", 500)
        page.wait_for_function(
            "() => { const el = document.getElementById('buyMsg'); "
            "return el && el.textContent.indexOf('Quantité minimale') !== -1; }",
            timeout=6000)
        msg = norm(page.locator("#buyMsg").inner_text())
        check("ajout: qty < 2000 → erreur visible", "Quantité minimale" in msg and "2 000" in msg)
        check("ajout: badge inchangé après erreur",
              norm(page.locator(".cart-count").inner_text()).strip() == "2 000")
        page.screenshot(path=os.path.join(SHOT, "02-produit.png"))

        # ── Panier : palier 2000 → 0,50 $ ──
        page.goto(URL + "/panier", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        check("panier: 1 ligne", page.locator(".cart-row").count() == 1)
        cart = norm(page.inner_text(".cart-summary"))
        check("panier: palier 2000 → 0,50 $/pièce",
              "0,50" in page.inner_text(".cart-info") and "2 000 pièces et +" in norm(page.inner_text(".cart-info")))
        check("panier: sous-total 1000,00", "1 000,00" in cart)
        check("panier: livraison incluse", 'free">Incluse' in page.content())
        check("panier: total 1000,00", "1 000,00" in cart and "Total" in cart)

        # ── Panier : palier 5000 → 0,42 $ ──
        page.fill(".qty-input", "5000")
        page.press(".qty-input", "Enter")
        page.wait_for_timeout(1200)
        cart5 = norm(page.inner_text(".cart-summary"))
        check("panier: palier 5000 → 0,42 $/pièce",
              "0,42" in page.inner_text(".cart-info") and "5 000 pièces et +" in norm(page.inner_text(".cart-info")))
        check("panier: total 2100,00", "2 100,00" in cart5)

        # ── Panier : 10 000 → toujours 0,42 $ (palier max) ──
        page.fill(".qty-input", "10000")
        page.press(".qty-input", "Enter")
        page.wait_for_timeout(1200)
        check("panier: 10 000 → 0,42 $/pièce (total 4200,00)",
              "0,42" in page.inner_text(".cart-info") and "4 200,00" in norm(page.inner_text(".cart-summary")))

        # remise à 5000 pour la commande
        page.fill(".qty-input", "5000")
        page.press(".qty-input", "Enter")
        page.wait_for_timeout(1200)
        page.screenshot(path=os.path.join(SHOT, "03-panier.png"))

        # ── Commande : virement ──
        page.goto(URL + "/commande", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        check("commande: recap 1 ligne", page.locator(".summary-item").count() == 1)
        check("commande: carte active par défaut",
              page.locator("#panel-carte").evaluate("el => el.classList.contains('active')"))
        page.check("input[name='payment_method'][value='virement']", force=True)
        page.wait_for_timeout(400)
        check("commande: panneau virement + champs carte non requis",
              page.locator("#panel-virement").evaluate("el => el.classList.contains('active')")
              and page.evaluate("!document.getElementById('card_number').required"))
        fill_co(page, "virement")
        page.locator("#checkoutForm button[type=submit]").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        conf = norm(page.inner_text("body"))
        check("confirmation: virement — statut + banque + ref",
              "En attente de réception du virement" in conf
              and "Tery-Emballage Inc." in conf and "Banque Nationale du Canada" in conf
              and re.search(r"TE-\d{8}-\d{4}", conf) is not None)
        page.screenshot(path=os.path.join(SHOT, "04-confirmation-virement.png"))

        # ── Commande : carte (à la livraison) ──
        page.goto(URL + "/produit/sac-transparent", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        check("produit 2: specs transparent",
              all(x in norm(page.inner_text("body")) for x in ["80 × 115 cm", "108 g", "Chargement de chaussures"]))
        check("produit 2: galerie 3 images (produit + pile + usage)",
              page.locator(".gallery-thumb").count() == 3
              and page.locator(".gallery-thumb img").nth(2).get_attribute("src").endswith("sac-transparent-usage.jpg"))
        add_product(page, "sac-transparent", 2000)
        page.goto(URL + "/commande", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        check("commande 2: recap nom produit", "Sac PP tissé transparent" in norm(page.inner_text(".checkout-summary")))
        fill_co(page, "carte")
        page.locator("#checkoutForm button[type=submit]").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        conf2 = norm(page.inner_text("body"))
        check("confirmation: carte — à la livraison + last4",
              "Confirmée — paiement par carte à la livraison" in conf2 and "4242" in conf2)
        page.screenshot(path=os.path.join(SHOT, "05-confirmation-carte.png"))

        # ── Commande : espèces ──
        page.goto(URL + "/produit/feuille-pp", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        check("produit 3: specs feuille",
              all(x in norm(page.inner_text("body")) for x in ["105 × 135 cm", "95 g", "Balles de vêtements", "Laminée"]))
        add_product(page, "feuille-pp", 2000)
        page.goto(URL + "/commande", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        fill_co(page, "especes")
        page.locator("#checkoutForm button[type=submit]").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        conf3 = norm(page.inner_text("body"))
        check("confirmation: espèces — à la livraison",
              "À régler à la livraison (espèces)" in conf3)
        page.screenshot(path=os.path.join(SHOT, "06-confirmation-especes.png"))

        # ── Validation serveur : mauvais code postal ──
        page.goto(URL + "/produit/sac-blanc", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        add_product(page, "sac-blanc", 2000)
        page.goto(URL + "/commande", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        fill_co(page, "virement", postal="ZZZ")
        page.locator("#checkoutForm button[type=submit]").click()
        page.wait_for_timeout(1000)
        vbody = norm(page.inner_text("body"))
        check("validation: mauvais code postal → erreur",
              "code postal doit respecter" in vbody)
        check("validation: champs préservés",
              page.input_value("#first_name") == "Test" and page.input_value("#city") == "Montréal")
        page.screenshot(path=os.path.join(SHOT, "07-validation.png"))

        # ── Panier vide après commande ──
        # (le test de validation a laissé 2 000 sacs-blancs : on les retire)
        page.goto(URL + "/panier", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.locator(".cart-remove").first.click()
        page.wait_for_timeout(800)
        check("panier: vide après commande", "Votre panier est vide" in norm(page.inner_text("body")))
        check("aucune erreur JS", not [e for e in errs if e.startswith("PAGEERROR")])

        # ═══════════ MOBILE 390x844 ═══════════
        mctx = browser.new_context(viewport={"width": 390, "height": 844})
        mpage = mctx.new_page()
        merrs = []
        mpage.on("pageerror", lambda e: merrs.append("PAGEERROR: " + str(e)))
        mpage.goto(URL, wait_until="domcontentloaded")
        mpage.wait_for_timeout(1500)
        check("mobile: pas de débordement",
              mpage.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        check("mobile: nav cachée", mpage.locator(".nav").is_hidden())
        check("mobile: 3 cartes produits", mpage.locator(".product-card").count() == 3)
        check("mobile: pas de pageerror", not [e for e in merrs if e.startswith("PAGEERROR")])
        mpage.goto(URL + "/produit/sac-blanc", wait_until="domcontentloaded")
        mpage.wait_for_timeout(1000)
        check("mobile: pas de débordement produit",
              mpage.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        mpage.screenshot(path=os.path.join(SHOT, "08-mobile.png"))
        mctx.close()

        # ── DB : 3 commandes persistées ──
        with sqlite3.connect(DB) as c:
            rows = c.execute("SELECT payment_method, total, subtotal FROM orders WHERE email = ?", (EMAIL,)).fetchall()
        check("db: 3 commandes test", len(rows) == 3, f"trouvé {len(rows)}")
        methods = sorted(r[0] for r in rows)
        check("db: 3 méthodes distinctes", methods == ["carte", "especes", "virement"], str(methods))
        check("db: totaux persistés (virement 2100,00)",
              any(abs(r[2] - 2100.0) < 0.01 for r in rows if r[0] == "virement"))
        with sqlite3.connect(DB) as c:
            items = c.execute(
                "SELECT product_name, price, qty FROM order_items oi JOIN orders o ON oi.order_id = o.id WHERE o.email = ?",
                (EMAIL,)).fetchall()
        check("db: lignes d'articles avec prix/qty",
              len(items) == 3 and all(i[1] > 0 and i[2] >= 2000 for i in items), str(items))
        check("db: aucun article à moins de 2000 pièces", all(i[2] >= 2000 for i in items))

        # ═══════════ ADMIN ═══════════
        page.goto(URL + "/admin", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        check("admin: anonyme redirigé login (next conservé)",
              "/admin/login" in page.url and "next=" in page.url, page.url)
        check("admin: titre login", "Administration" in page.title())
        # mauvais mot de passe
        page.fill("#email", "admin@tery.shop")
        page.fill("#password", "mauvais-mot-de-passe")
        page.locator(".admin-login button[type=submit]").click()
        page.wait_for_timeout(1000)
        check("admin: mauvais mot de passe → erreur",
              "incorrect" in norm(page.inner_text("body")))
        # bon login → tableau
        page.fill("#email", "admin@tery.shop")
        page.fill("#password", "admin123")
        page.locator(".admin-login button[type=submit]").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        abody = norm(page.inner_text("body"))
        check("admin: connecté → tableau", "/admin" in page.url and "Commandes" in abody)
        check("admin: 3 commandes affichées",
              page.locator(".admin-table tbody tr").count() >= 3,
              str(page.locator(".admin-table tbody tr").count()))
        check("admin: refs TE- présentes", abody.count("TE-") >= 3)
        # modal détails (titres rendus en majuscules par le CSS)
        page.locator(".admin-detail").first.click()
        page.wait_for_timeout(500)
        modal = norm(page.inner_text("#adminModal")).upper()
        check("admin: modal détails (client/articles/total)",
              "COMMANDE TE-" in modal and "LIVRAISON" in modal
              and "ARTICLES" in modal and "TOTAL" in modal, modal[:80])
        page.screenshot(path=os.path.join(SHOT, "10-admin.png"))
        page.locator("#mClose").click()
        page.wait_for_timeout(300)
        # logout → zone protégée
        page.goto(URL + "/admin/logout", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        check("admin: logout → login", "/admin/login" in page.url)
        page.goto(URL + "/admin", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        check("admin: /admin protégé après logout",
              "/admin/login" in page.url and "next=" in page.url, page.url)

        # ── Nettoyage ──
        with sqlite3.connect(DB) as c:
            c.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE email = ?)", (EMAIL,))
            c.execute("DELETE FROM orders WHERE email = ?", (EMAIL,))
        check("db: nettoyage — retour au niveau de base",
              db_orders() == BASE_ORDERS, f"{db_orders()} != {BASE_ORDERS}")

        ctx.close()
        browser.close()

    print("\n" + "═" * 60)
    print(f"RÉSULTAT : {len(PASS_LINES)} PASS, {len(FAIL_LINES)} FAIL")
    for f in FAIL_LINES:
        print("  ✗ " + f)
    if FAIL_LINES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
