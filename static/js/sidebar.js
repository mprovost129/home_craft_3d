(function () {
  function toggle(targetId, btn) {
    const el = document.getElementById(targetId);
    if (!el) return;

    const isHidden = el.hasAttribute("hidden");
    if (isHidden) {
      el.removeAttribute("hidden");
      btn.setAttribute("aria-expanded", "true");
      btn.textContent = "▾";
    } else {
      el.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", "false");
      btn.textContent = "▸";
    }
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".hc3-tree-toggle");
    if (!btn) return;

    const targetId = btn.getAttribute("data-target");
    if (!targetId) return;

    toggle(targetId, btn);
  });
})();
