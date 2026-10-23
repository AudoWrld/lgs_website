(function () {
  function init(root) {
    const perPage = parseInt(root.getAttribute("data-per-page") || "10", 10);
    const label = root.getAttribute("data-label") || "rows";
    const rows = Array.prototype.slice.call(
      root.querySelectorAll("tbody tr[data-row]"),
    );
    const searchInput = root.querySelector("[data-search-input]");
    const filters = Array.prototype.slice.call(
      root.querySelectorAll("[data-filter]"),
    );
    const clearBtn = root.querySelector("[data-clear]");
    const info = root.querySelector("[data-info]");
    const pager = root.querySelector("[data-pager]");
    const noMatch = root.querySelector("tr[data-no-match]");
    let page = 1;
    let search = "";
    let filterValues = {};
    filters.forEach(function (f) {
      filterValues[f.getAttribute("data-filter")] = "";
    });

    function matches(row) {
      if (
        search &&
        (row.getAttribute("data-search") || "")
          .toLowerCase()
          .indexOf(search) === -1
      )
        return false;
      for (var k in filterValues) {
        if (filterValues[k] && row.dataset[k] !== filterValues[k]) return false;
      }
      return true;
    }

    function update() {
      const visible = rows.filter(matches);
      const total = visible.length;
      const pages = Math.max(1, Math.ceil(total / perPage));
      if (page > pages) page = pages;
      const start = (page - 1) * perPage;
      const end = Math.min(start + perPage, total);
      rows.forEach(function (r) {
        r.setAttribute("hidden", "");
      });
      visible.forEach(function (r, i) {
        if (i >= start && i < end) r.removeAttribute("hidden");
      });
      if (noMatch) {
        if (total === 0 && rows.length > 0) noMatch.removeAttribute("hidden");
        else noMatch.setAttribute("hidden", "");
      }
      const hasActive =
        !!search ||
        Object.keys(filterValues).some(function (k) {
          return !!filterValues[k];
        });
      if (clearBtn) {
        if (hasActive) clearBtn.removeAttribute("hidden");
        else clearBtn.setAttribute("hidden", "");
      }
      if (info) {
        if (total === 0) info.textContent = "Showing 0 of 0 " + label;
        else
          info.textContent =
            "Showing " + (start + 1) + "-" + end + " of " + total + " " + label;
      }
      if (pager) {
        pager.innerHTML = "";
        const prev = document.createElement("button");
        prev.className = "br-btn br-btn-sm";
        prev.textContent = "Previous";
        prev.disabled = page === 1;
        prev.addEventListener("click", function () {
          page--;
          update();
        });
        pager.appendChild(prev);
        const nums = [];
        for (var p = 1; p <= pages; p++) {
          if (p === 1 || p === pages || Math.abs(p - page) <= 1) nums.push(p);
        }
        let last = 0;
        nums.forEach(function (n) {
          if (n - last > 1) {
            const e = document.createElement("span");
            e.textContent = "…";
            e.className = "br-btn br-btn-sm";
            pager.appendChild(e);
          }
          const b = document.createElement("button");
          b.className =
            "br-btn br-btn-sm" + (n === page ? " br-btn-primary" : "");
          b.textContent = n;
          b.addEventListener("click", function () {
            page = n;
            update();
          });
          pager.appendChild(b);
          last = n;
        });
        const next = document.createElement("button");
        next.className = "br-btn br-btn-sm";
        next.textContent = "Next";
        next.disabled = page === pages;
        next.addEventListener("click", function () {
          page++;
          update();
        });
        pager.appendChild(next);
      }
    }

    if (searchInput) {
      searchInput.addEventListener("input", function () {
        search = searchInput.value.toLowerCase();
        page = 1;
        update();
      });
    }
    filters.forEach(function (f) {
      f.addEventListener("change", function () {
        filterValues[f.getAttribute("data-filter")] = f.value;
        page = 1;
        update();
      });
    });
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (searchInput) searchInput.value = "";
        search = "";
        filters.forEach(function (f) {
          f.value = "";
          filterValues[f.getAttribute("data-filter")] = "";
        });
        page = 1;
        update();
      });
    }
    const form = root.querySelector("form");
    if (form)
      form.addEventListener("submit", function (e) {
        e.preventDefault();
      });

    update();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-table-pager]").forEach(init);
  });
})();
