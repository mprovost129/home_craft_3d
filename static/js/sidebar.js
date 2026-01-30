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

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".hc3-tree-toggle");
    if (!btn) return;

    const targetId = btn.getAttribute("data-target");
    if (!targetId) return;

    toggle(targetId, btn);
  });
})();
