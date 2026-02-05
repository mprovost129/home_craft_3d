// static/js/sidebar_filter.js
(function () {
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function setHidden(el, hidden) {
    if (!el) return;
    if (hidden) el.setAttribute("hidden", "");
    else el.removeAttribute("hidden");
  }

  function showAllParentsAndChildren() {
    qsa(".hc3-filter-parent").forEach(function (p) {
      p.removeAttribute("hidden");
      qsa(".hc3-filter-child", p).forEach(function (c) {
        c.removeAttribute("hidden");
      });
    });
  }

  function collapseAllTrees() {
    qsa(".hc3-tree-children").forEach(function (ul) {
      ul.setAttribute("hidden", "");
    });
    qsa(".hc3-tree-toggle").forEach(function (btn) {
      btn.setAttribute("aria-expanded", "false");
      // Let existing sidebar.js handle icon on click; we only reset state here.
      var icon = btn.querySelector("i");
      if (icon) {
        icon.classList.remove("bi-caret-down-fill");
        icon.classList.add("bi-caret-right-fill");
      }
    });
  }

  function expandTreeFor(btn) {
    if (!btn) return;
    var targetId = btn.getAttribute("data-target");
    if (!targetId) return;
    var ul = document.getElementById(targetId);
    if (!ul) return;

    ul.removeAttribute("hidden");
    btn.setAttribute("aria-expanded", "true");

    var icon = btn.querySelector("i");
    if (icon) {
      icon.classList.remove("bi-caret-right-fill");
      icon.classList.add("bi-caret-down-fill");
    }
  }

  function openMoreDetailsWhileSearching(isSearching) {
    ["hc3ModelsMore", "hc3FilesMore"].forEach(function (id) {
      var details = document.getElementById(id);
      if (!details) return;
      if (isSearching) details.open = true;
      // Don’t auto-close on clear; that can feel jarring. If you want, we can close it.
    });
  }

  function applyFilter(termRaw) {
    var term = (termRaw || "").trim().toLowerCase();
    var searching = term.length > 0;

    openMoreDetailsWhileSearching(searching);

    if (!searching) {
      showAllParentsAndChildren();
      // Keep the user’s expand/collapse choices; don’t force collapse on clear.
      return;
    }

    qsa(".hc3-filter-parent").forEach(function (parentLi) {
      var parentName = (parentLi.getAttribute("data-name") || "").toLowerCase();
      var parentMatches = parentName.indexOf(term) !== -1;

      var childLis = qsa(".hc3-filter-child", parentLi);
      var anyChildMatches = false;

      childLis.forEach(function (childLi) {
        var childName = (childLi.getAttribute("data-name") || "").toLowerCase();
        var childMatches = childName.indexOf(term) !== -1;
        setHidden(childLi, !childMatches);
        if (childMatches) anyChildMatches = true;
      });

      // Parent is visible if parent matches OR any child matches
      var showParent = parentMatches || anyChildMatches;
      setHidden(parentLi, !showParent);

      // If we’re showing because of a child match, auto-expand so the match is visible
      if (anyChildMatches) {
        var btn = parentLi.querySelector(".hc3-tree-toggle");
        if (btn) expandTreeFor(btn);
      }

      // If parent matches but no children match, we keep children collapsed unless already open
      // (no forced behavior needed)
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var input = document.getElementById("hc3SidebarFilter");
    var clearBtn = document.getElementById("hc3SidebarFilterClear");
    if (!input) return;

    // If the sidebar is cached between pages, ensure filter starts clean
    input.value = "";

    input.addEventListener("input", function () {
      applyFilter(input.value);
    });

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        input.value = "";
        applyFilter("");
        input.focus();
      });
    }
  });
})();
