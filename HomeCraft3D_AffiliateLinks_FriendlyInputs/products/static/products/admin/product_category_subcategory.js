// products/static/products/admin/product_category_subcategory.js
(function () {
  function $(selector) {
    return document.querySelector(selector);
  }

  function clearOptions(selectEl, placeholderText) {
    while (selectEl.options.length) {
      selectEl.remove(0);
    }
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

  async function fetchSubcategories(endpointUrl, categoryId) {
    const url = new URL(endpointUrl, window.location.origin);
    url.searchParams.set("category_id", String(categoryId));

    const resp = await fetch(url.toString(), {
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });

    if (!resp.ok) return [];
    const data = await resp.json();
    return (data && data.results) ? data.results : [];
  }

  function getEndpointUrl() {
    // We are inside /admin/products/product/add/ or /admin/products/product/<id>/change/
    // Our endpoint is registered relative to ProductAdmin URLs:
    // /admin/products/product/subcategories-for-category/
    const parts = window.location.pathname.split("/").filter(Boolean);
    // find ".../admin/products/product/..."
    const adminIdx = parts.indexOf("admin");
    if (adminIdx === -1) return null;

    // Rebuild base: /admin/products/product/
    // parts = ["admin","products","product","add"] OR ["admin","products","product","<id>","change"]
    if (parts.length < adminIdx + 3) return null;

    const base = "/" + parts.slice(0, adminIdx + 3).join("/") + "/";
    return base + "subcategories-for-category/";
  }

  async function refreshSubcategoryOptions() {
    const categoryEl = $("#id_category");
    const subcategoryEl = $("#id_subcategory");
    if (!categoryEl || !subcategoryEl) return;

    const endpointUrl = getEndpointUrl();
    if (!endpointUrl) return;

    const selectedCategory = categoryEl.value;
    const currentSubcategory = subcategoryEl.value;

    if (!selectedCategory) {
      clearOptions(subcategoryEl, "— Select a category first —");
      return;
    }

    clearOptions(subcategoryEl, "Loading…");

    const rows = await fetchSubcategories(endpointUrl, selectedCategory);

    clearOptions(subcategoryEl, "---------");
    for (const row of rows) {
      addOption(subcategoryEl, row.id, row.text);
    }

    // Preserve selection if still valid (e.g., form re-render after validation error)
    if (currentSubcategory) {
      const exists = Array.from(subcategoryEl.options).some((o) => o.value === String(currentSubcategory));
      if (exists) subcategoryEl.value = String(currentSubcategory);
    }
  }

  function init() {
    const categoryEl = $("#id_category");
    const subcategoryEl = $("#id_subcategory");
    if (!categoryEl || !subcategoryEl) return;

    // If no category is selected on initial load, keep subcategory empty/placeholder.
    if (!categoryEl.value) {
      clearOptions(subcategoryEl, "— Select a category first —");
    } else {
      // Page load with an existing value (change page) or after validation errors
      refreshSubcategoryOptions();
    }

    categoryEl.addEventListener("change", function () {
      // When category changes, we should also wipe the current subcategory selection.
      subcategoryEl.value = "";
      refreshSubcategoryOptions();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
