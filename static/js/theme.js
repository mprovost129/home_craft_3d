// static/js/theme.js
(function () {
  function getDefaultModeFromSite() {
    const v = getComputedStyle(document.documentElement).getPropertyValue("--hc-default-mode").trim();
    const cleaned = v.replaceAll('"', "").replaceAll("'", "");
    return cleaned === "dark" ? "dark" : "light";
  }

  function getMode() {
    const saved = localStorage.getItem("hc-theme");
    if (saved === "light" || saved === "dark") return saved;
    return getDefaultModeFromSite();
  }

  function applyMode(mode) {
    document.documentElement.setAttribute("data-bs-theme", mode);
    localStorage.setItem("hc-theme", mode);
    const btn = document.getElementById("hcThemeToggle");
    if (btn) {
      btn.innerHTML = mode === "dark" ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon-stars"></i>';
      btn.title = mode === "dark" ? "Switch to light mode" : "Switch to dark mode";
      btn.setAttribute("aria-pressed", mode === "dark" ? "true" : "false");
    }
  }

  // prevent flash
  applyMode(getMode());

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("hcThemeToggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      const current = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "dark" : "light";
      applyMode(current === "dark" ? "light" : "dark");
    });
  });
})();
