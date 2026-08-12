/* TERY-EMBALLAGE — interactions boutique (vente en gros) */
(function () {
  "use strict";

  /* ── Ajout au panier en AJAX (dégradation : POST classique) ── */
  document.querySelectorAll("form.js-add-cart").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = form.querySelector("button[type=submit]");
      var original = btn.textContent;
      var msg = document.getElementById("buyMsg");
      if (msg) msg.textContent = "";
      btn.disabled = true;
      btn.textContent = "Ajouté ✓";
      fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new FormData(form)
      })
        .then(function (res) {
          if (!res.ok) {
            return res.json().then(function (data) {
              throw new Error(data.error || "http " + res.status);
            });
          }
          return res.json().then(function (data) {
            if (data.ok) bumpCart(data.qty || 1);
          });
        })
        .catch(function (err) {
          btn.disabled = false;
          btn.textContent = original;
          if (err && err.message && err.message.indexOf("http ") !== 0) {
            // erreur métier (ex. quantité minimale) : message local
            if (msg) msg.textContent = err.message;
          } else {
            // repli : soumission classique (navigation complète)
            form.submit();
          }
        });
      setTimeout(function () {
        if (btn.disabled) {
          btn.disabled = false;
          btn.textContent = original;
        }
      }, 1400);
    });
  });

  function bumpCart(qty) {
    var el = document.querySelector(".cart-count");
    if (!el) return;
    var n = parseInt(el.textContent.replace(/\D/g, ""), 10) || 0;
    el.textContent = (n + qty).toLocaleString("fr-CA").replace(/\u00A0/g, "\u202F");
    el.classList.remove("bump");
    void el.offsetWidth;
    el.classList.add("bump");
  }

  /* ── Steppers de quantité (produit : ajuste, panier : soumet) ── */
  document.querySelectorAll(".qty-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var form = btn.closest("form");
      if (!form) return;
      var input = form.querySelector(".qty-input");
      var step = parseInt(btn.dataset.step, 10);
      var min = parseInt(btn.dataset.min || input.getAttribute("min") || "1", 10);
      var qty = Math.max(min, (parseInt(input.value, 10) || min) + step);
      input.value = qty;
      if (form.classList.contains("qty-form")) form.submit();
    });
  });

  /* ── Méthodes de paiement (commande) ── */
  var CARD_FIELDS = ["card_name", "card_number", "card_expiry", "card_cvc"];

  function togglePanels() {
    var checked = document.querySelector('input[name="payment_method"]:checked');
    if (!checked) return;
    ["carte", "virement", "especes"].forEach(function (key) {
      var panel = document.getElementById("panel-" + key);
      if (panel) panel.classList.toggle("active", key === checked.value);
    });
    CARD_FIELDS.forEach(function (name) {
      var input = document.getElementById(name);
      if (input) input.required = (checked.value === "carte");
    });
  }

  document.querySelectorAll('input[name="payment_method"]').forEach(function (radio) {
    radio.addEventListener("change", togglePanels);
  });
  togglePanels();

  /* ── Formatage carte bancaire ── */
  var cardNumber = document.getElementById("card_number");
  if (cardNumber) {
    cardNumber.addEventListener("input", function () {
      var digits = this.value.replace(/\D/g, "").slice(0, 19);
      this.value = digits.replace(/(.{4})/g, "$1 ").trim();
    });
  }
  var cardExpiry = document.getElementById("card_expiry");
  if (cardExpiry) {
    cardExpiry.addEventListener("input", function () {
      var digits = this.value.replace(/\D/g, "").slice(0, 4);
      this.value = digits.length > 2 ? digits.slice(0, 2) + "/" + digits.slice(2) : digits;
    });
  }
  var cardCvc = document.getElementById("card_cvc");
  if (cardCvc) {
    cardCvc.addEventListener("input", function () {
      this.value = this.value.replace(/\D/g, "").slice(0, 4);
    });
  }

  /* ── Carrousels d'images (hero : 3 produits, cartes : produit ↔ usage) ── */
  document.querySelectorAll("[data-carousel]").forEach(function (carousel) {
    var slides = carousel.querySelectorAll(".carousel-slide");
    if (slides.length < 2) return;
    setInterval(function () {
      var active = carousel.querySelector(".carousel-slide.active");
      var next = active && active.nextElementSibling ? active.nextElementSibling : slides[0];
      active.classList.remove("active");
      next.classList.add("active");
    }, 3500);
  });

  /* ── Galerie produit (miniatures) ── */
  var galleryMain = document.getElementById("galleryMain");
  document.querySelectorAll(".gallery-thumb").forEach(function (thumb) {
    thumb.addEventListener("click", function () {
      if (!galleryMain) return;
      galleryMain.src = thumb.dataset.full;
      galleryMain.alt = thumb.dataset.alt || galleryMain.alt;
      document.querySelectorAll(".gallery-thumb").forEach(function (t) {
        t.classList.toggle("active", t === thumb);
      });
    });
  });
})();
