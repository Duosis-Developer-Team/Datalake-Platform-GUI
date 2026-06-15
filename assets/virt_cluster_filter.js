/**
 * Client-side search filter for virt cluster checkbox popover panels.
 * Filters .virt-cluster-checkbox-item rows by data-label without server round-trips.
 */
(function () {
  function filterClusterPanel(input) {
    const panel = input.closest(".virt-cluster-filter-panel");
    if (!panel) {
      return;
    }
    const query = (input.value || "").toLowerCase().trim();
    panel.querySelectorAll(".virt-cluster-checkbox-item").forEach(function (el) {
      const label = (el.getAttribute("data-label") || "").toLowerCase();
      el.style.display = !query || label.includes(query) ? "" : "none";
    });
  }

  document.addEventListener("input", function (event) {
    const target = event.target;
    if (!target || target.tagName !== "INPUT") {
      return;
    }
    const panel = target.closest(".virt-cluster-filter-panel");
    if (panel) {
      filterClusterPanel(target);
    }
  });
})();
