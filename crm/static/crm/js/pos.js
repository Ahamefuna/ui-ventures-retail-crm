/* Interactive POS Cart, Category Pills & Loyalty Point Redemption Engine */

document.addEventListener("DOMContentLoaded", () => {
  const customersDataEl = document.getElementById("pos-customers-data");
  const productsDataEl = document.getElementById("pos-products-data");
  if (!customersDataEl || !productsDataEl) return;

  const customers = JSON.parse(customersDataEl.textContent);
  const products = JSON.parse(productsDataEl.textContent);
  const POINT_VALUE = Number(document.getElementById("posForm")?.dataset.pointValue || 10);

  const customerMap = new Map(customers.map((c) => [String(c.id), c]));
  const productMap = new Map(products.map((p) => [String(p.id), p]));

  const customerSelect = document.getElementById("posCustomerSelect");
  const customerSearch = document.getElementById("posCustomerSearch");
  const customerInfoBox = document.getElementById("posCustomerInfo");
  const customerPointsEl = document.getElementById("posCustomerPoints");
  const customerNairaEl = document.getElementById("posCustomerNaira");
  const customerCategoryEl = document.getElementById("posCustomerCategory");
  const customerTierBadge = document.getElementById("posCustomerTierBadge");

  const productSearch = document.getElementById("posProductSearch");
  const categoryPills = Array.from(document.querySelectorAll("[data-pos-cat]"));
  const productCards = Array.from(document.querySelectorAll(".pos-product-item"));
  const emptyCatalogMsg = document.getElementById("posCatalogEmpty");

  const cartBody = document.getElementById("posCartBody");
  const cartEmpty = document.getElementById("posCartEmpty");
  const cartCountBadge = document.getElementById("posCartCountBadge");
  const cartPayloadInput = document.getElementById("posCartPayload");
  const pointsInput = document.getElementById("posPointsInput");
  const maxPointsHint = document.getElementById("posMaxPointsHint");
  const applyMaxBtn = document.getElementById("posApplyMaxPoints");

  const grossEl = document.getElementById("posGrossTotal");
  const discountEl = document.getElementById("posDiscountTotal");
  const netEl = document.getElementById("posNetTotal");
  const earnedEl = document.getElementById("posEstimatedEarn");
  const submitBtn = document.getElementById("posSubmitBtn");
  const paymentRefInput = document.getElementById("posPaymentRef");
  const payMethodBtns = Array.from(document.querySelectorAll("[data-pay-prefix]"));
  const genRefBtn = document.getElementById("posGenRefBtn");
  const clearCartBtn = document.getElementById("posClearCartBtn");

  let activeCategory = "";
  let activePayPrefix = "POS";
  const cart = new Map();

  const fmtNaira = (amount) =>
    "₦" +
    Number(amount || 0).toLocaleString("en-NG", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const getSelectedCustomer = () => {
    const id = customerSelect?.value;
    return id ? customerMap.get(String(id)) || null : null;
  };

  const getGrossTotal = () => {
    let total = 0;
    cart.forEach((qty, pid) => {
      const prod = productMap.get(pid);
      if (prod) total += prod.unit_price * qty;
    });
    return Math.round(total * 100) / 100;
  };

  const computeMaxRedeemablePoints = (customer, gross) => {
    if (!customer || gross <= 0 || customer.loyalty_points <= 0) return 0;
    const capNaira = Math.floor(gross * 0.5 * 100) / 100;
    const capPoints = Math.floor(capNaira / POINT_VALUE);
    return Math.max(0, Math.min(customer.loyalty_points, capPoints));
  };

  const tierClassFor = (tier) => {
    if (tier === "Champions") return "badge-tier-champions";
    if (tier === "Loyal Customers") return "badge-tier-loyal";
    if (tier === "Potential Loyalists") return "badge-tier-potential";
    if (tier === "At-Risk / Dormant") return "badge-tier-atrisk";
    return "badge-tier-neutral";
  };

  const updateCustomerPanel = () => {
    const cust = getSelectedCustomer();
    if (!cust) {
      customerInfoBox.classList.add("d-none");
      pointsInput.value = 0;
      pointsInput.max = 0;
    } else {
      customerInfoBox.classList.remove("d-none");
      customerPointsEl.textContent = `${cust.loyalty_points.toLocaleString()} pts`;
      customerNairaEl.textContent = fmtNaira(cust.loyalty_points * POINT_VALUE);
      customerCategoryEl.textContent = `${cust.cust_code} · ${cust.category}`;
      if (customerTierBadge) {
        customerTierBadge.textContent = cust.rfm_tier || "Unsegmented";
        customerTierBadge.className = `uiv-badge ${tierClassFor(cust.rfm_tier)}`;
      }
    }
    updateTotals();
  };

  const updateTotals = () => {
    const cust = getSelectedCustomer();
    const gross = getGrossTotal();
    const maxPts = computeMaxRedeemablePoints(cust, gross);

    pointsInput.max = maxPts;
    let pts = parseInt(pointsInput.value || "0", 10);
    if (Number.isNaN(pts) || pts < 0) pts = 0;
    if (pts > maxPts) {
      pts = maxPts;
      pointsInput.value = maxPts;
    }

    const discount = pts * POINT_VALUE;
    const net = Math.max(0, Math.round((gross - discount) * 100) / 100);
    const estEarn = Math.floor(net * 0.01);

    maxPointsHint.textContent = cust
      ? `Max redeemable (50% cap): ${maxPts.toLocaleString()} pts (${fmtNaira(maxPts * POINT_VALUE)})`
      : "Select a customer to view redeemable points.";

    grossEl.textContent = fmtNaira(gross);
    discountEl.textContent = "-" + fmtNaira(discount);
    netEl.textContent = fmtNaira(net);
    earnedEl.textContent = `+${estEarn.toLocaleString()} pts`;

    const payload = [];
    let totalQty = 0;
    cart.forEach((qty, pid) => {
      payload.push({ product_id: Number(pid), quantity: qty });
      totalQty += qty;
    });
    if (cartCountBadge) {
      cartCountBadge.textContent = `${totalQty} item${totalQty === 1 ? "" : "s"}`;
    }
    cartPayloadInput.value = JSON.stringify(payload);
    submitBtn.disabled = !cust || cart.size === 0;
  };

  const renderCart = () => {
    cartBody.innerHTML = "";
    if (cart.size === 0) {
      cartEmpty.classList.remove("d-none");
    } else {
      cartEmpty.classList.add("d-none");
      cart.forEach((qty, pid) => {
        const prod = productMap.get(pid);
        if (!prod) return;
        const tr = document.createElement("tr");
        const subtotal = prod.unit_price * qty;
        tr.innerHTML = `
          <td>
            <div class="fw-semibold text-dark small">${prod.product_name}</div>
            <div class="text-muted" style="font-size: 0.74rem;">${prod.sku_code} · ${fmtNaira(prod.unit_price)}</div>
          </td>
          <td class="text-center">
            <div class="btn-group btn-group-sm" role="group">
              <button type="button" class="btn btn-outline-secondary" data-cart-dec="${pid}" aria-label="Decrease quantity">-</button>
              <span class="btn btn-light disabled fw-bold px-2">${qty}</span>
              <button type="button" class="btn btn-outline-secondary" data-cart-inc="${pid}" aria-label="Increase quantity">+</button>
            </div>
          </td>
          <td class="text-end fw-semibold tabular-nums small">${fmtNaira(subtotal)}</td>
          <td class="text-end">
            <button type="button" class="btn btn-sm btn-link text-danger p-0" data-cart-rem="${pid}" aria-label="Remove item">
              <i class="bi bi-x-circle-fill"></i>
            </button>
          </td>
        `;
        cartBody.appendChild(tr);
      });
    }
    updateTotals();
  };

  document.querySelectorAll("[data-add-product]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-add-product");
      const prod = productMap.get(pid);
      if (!prod || prod.stock_qty <= 0) return;
      const current = cart.get(pid) || 0;
      if (current >= prod.stock_qty) {
        alert(`Only ${prod.stock_qty} unit(s) of ${prod.product_name} are in stock.`);
        return;
      }
      cart.set(pid, current + 1);
      renderCart();
    });
  });

  cartBody.addEventListener("click", (ev) => {
    const decBtn = ev.target.closest("[data-cart-dec]");
    const incBtn = ev.target.closest("[data-cart-inc]");
    const remBtn = ev.target.closest("[data-cart-rem]");

    if (decBtn) {
      const pid = decBtn.getAttribute("data-cart-dec");
      const next = (cart.get(pid) || 1) - 1;
      if (next <= 0) cart.delete(pid);
      else cart.set(pid, next);
      renderCart();
    } else if (incBtn) {
      const pid = incBtn.getAttribute("data-cart-inc");
      const prod = productMap.get(pid);
      const current = cart.get(pid) || 0;
      if (prod && current < prod.stock_qty) {
        cart.set(pid, current + 1);
        renderCart();
      }
    } else if (remBtn) {
      cart.delete(remBtn.getAttribute("data-cart-rem"));
      renderCart();
    }
  });

  if (customerSearch && customerSelect) {
    customerSearch.addEventListener("input", () => {
      const term = customerSearch.value.trim().toLowerCase();
      Array.from(customerSelect.options).forEach((opt, idx) => {
        if (idx === 0) return;
        const match = opt.textContent.toLowerCase().includes(term);
        opt.hidden = !match;
      });
    });
  }

  customerSelect?.addEventListener("change", updateCustomerPanel);
  pointsInput?.addEventListener("input", updateTotals);

  applyMaxBtn?.addEventListener("click", () => {
    const maxPts = computeMaxRedeemablePoints(getSelectedCustomer(), getGrossTotal());
    pointsInput.value = maxPts;
    updateTotals();
  });

  clearCartBtn?.addEventListener("click", () => {
    cart.clear();
    pointsInput.value = 0;
    renderCart();
  });

  const generatePaymentRef = (prefix = activePayPrefix) => {
    const now = new Date();
    const stamp = now.toISOString().replace(/[-:T.Z]/g, "").slice(2, 12);
    const rand = Math.random().toString(36).substring(2, 6).toUpperCase();
    return `${prefix}-${stamp}-${rand}`;
  };

  payMethodBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      activePayPrefix = btn.getAttribute("data-pay-prefix") || "POS";
      payMethodBtns.forEach((b) => b.classList.toggle("active", b === btn));
      if (paymentRefInput) {
        paymentRefInput.value = generatePaymentRef(activePayPrefix);
      }
    });
  });

  if (paymentRefInput && !paymentRefInput.value) {
    paymentRefInput.value = generatePaymentRef();
  }
  genRefBtn?.addEventListener("click", () => {
    paymentRefInput.value = generatePaymentRef();
  });

  const filterProducts = () => {
    const q = (productSearch?.value || "").trim().toLowerCase();
    let visibleCount = 0;
    productCards.forEach((card) => {
      const text = card.dataset.searchText || "";
      const cardCat = card.dataset.category || "";
      const visible = (!q || text.includes(q)) && (!activeCategory || cardCat === activeCategory);
      card.classList.toggle("d-none", !visible);
      if (visible) visibleCount++;
    });
    if (emptyCatalogMsg) {
      emptyCatalogMsg.classList.toggle("d-none", visibleCount > 0);
    }
  };

  categoryPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      activeCategory = pill.getAttribute("data-pos-cat") || "";
      categoryPills.forEach((p) => p.classList.toggle("active", p === pill));
      filterProducts();
    });
  });

  productSearch?.addEventListener("input", filterProducts);

  updateCustomerPanel();
  renderCart();
});
