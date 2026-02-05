(function () {
  function setIcon(btn, expanded) {
    const icon = btn.querySelector("i");
    if (!icon) return;

    icon.classList.remove("bi-caret-right-fill", "bi-caret-down-fill");
    icon.classList.add(expanded ? "bi-caret-down-fill" : "bi-caret-right-fill");
  }

  function toggle(targetId, btn) {
    const el = document.getElementById(targetId);
    if (!el) return;

    const isHidden = el.hasAttribute("hidden");
    if (isHidden) {
      el.removeAttribute("hidden");
      btn.setAttribute("aria-expanded", "true");
      setIcon(btn, true);
    } else {
      el.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", "false");
      setIcon(btn, false);
    }
  }

  // Toggle subcategory lists
  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".hc3-tree-toggle");
    if (!btn) return;

    const targetId = btn.getAttribute("data-target");
    if (!targetId) return;

    toggle(targetId, btn);
  });

  // Filter categories (Models + Files + children)
  function normalize(s) {
    return (s || "").toString().trim().toLowerCase();
  }

  function applySidebarFilter(query) {
    const q = normalize(query);

    const items = document.querySelectorAll(".hc3-filter-item");
    if (!items.length) return;

    // Show everything if empty
    if (!q) {
      items.forEach((li) => {
        li.style.display = "";
      });

      // Reset "More…" sections if user clears filter
      const modelsMore = document.getElementById("hc3ModelsMore");
      const filesMore = document.getElementById("hc3FilesMore");
      if (modelsMore) modelsMore.open = false;
      if (filesMore) filesMore.open = false;

      return;
    }

    let anyModelsHit = false;
    let anyFilesHit = false;

    items.forEach((li) => {
      const hay = normalize(li.getAttribute("data-filter"));
      const match = hay.includes(q);

      li.style.display = match ? "" : "none";

      // Auto-open "More…" if a hit is inside it
      // (We detect this by walking up to the details containers.)
      if (match) {
        const inModelsMore = li.closest("#hc3ModelsMore");
        const inFilesMore = li.closest("#hc3FilesMore");
        if (inModelsMore) anyModelsHit = true;
        if (inFilesMore) anyFilesHit = true;

        // Also open parents so child matches are visible
        const parentChildren = li.closest(".hc3-tree-children");
        if (parentChildren && parentChildren.hasAttribute("hidden")) {
          parentChildren.removeAttribute("hidden");
          const btn = document.querySelector(`[data-target="${parentChildren.id}"]`);
          if (btn) {
            btn.setAttribute("aria-expanded", "true");
            setIcon(btn, true);
          }
        }
      }
    });

    const modelsMore = document.getElementById("hc3ModelsMore");
    const filesMore = document.getElementById("hc3FilesMore");
    if (modelsMore) modelsMore.open = anyModelsHit;
    if (filesMore) filesMore.open = anyFilesHit;
  }

  document.addEventListener("input", function (e) {
    const input = e.target.closest("#hc3SidebarFilter");
    if (!input) return;
    applySidebarFilter(input.value);
  });
})();
