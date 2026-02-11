// products/static/products/seller/category_subcategory.js
(function () {
  function byId(id) {
    return document.getElementById(id);
  }

  function clearOptions(selectEl, placeholderText) {
    while (selectEl.options.length) selectEl.remove(0);
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholderText || "---------";
    selectEl.appendChild(opt);
  }

  function addOption(selectEl, value, text) {
    const opt = document.createElement("option");
    opt.value = String(value);
    opt.textContent = text;
    selectEl.appendChild(opt);
  }

  async function fetchSubcategories(url, categoryId) {
    const u = new URL(url, window.location.origin);
    u.searchParams.set("category_id", String(categoryId));
    const resp = await fetch(u.toString(), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!resp.ok) return [];
    const data = await resp.json();
    return data && data.results ? data.results : [];
  }

  async function refresh() {
    const categoryEl = byId("id_category");
    const subcategoryEl = byId("id_subcategory");
    if (!categoryEl || !subcategoryEl) return;

    const endpoint = subcategoryEl.getAttribute("data-subcategory-endpoint");
    if (!endpoint) return;

    const categoryId = categoryEl.value;
    const current = subcategoryEl.value;

    if (!categoryId) {
      clearOptions(subcategoryEl, "— Select a category first —");
      return;
    }

    clearOptions(subcategoryEl, "Loading…");
    const rows = await fetchSubcategories(endpoint, categoryId);

    clearOptions(subcategoryEl, "---------");
    for (const row of rows) addOption(subcategoryEl, row.id, row.text);

    if (current) {
      const exists = Array.from(subcategoryEl.options).some((o) => o.value === String(current));
      if (exists) subcategoryEl.value = String(current);
    }
  }

  function init() {
    const categoryEl = byId("id_category");
    const subcategoryEl = byId("id_subcategory");
    if (!categoryEl || !subcategoryEl) return;

    if (!categoryEl.value) {
      clearOptions(subcategoryEl, "— Select a category first —");
    } else {
      refresh();
    }

    categoryEl.addEventListener("change", function () {
      subcategoryEl.value = "";
      refresh();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
