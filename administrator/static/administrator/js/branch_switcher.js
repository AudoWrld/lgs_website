(function () {
  var KEY = "lgs_admin_branch";
  var DEFAULT_ID = 1;

  var root = document.querySelector("[data-branch-switcher]");
  if (!root) return;

  var btn = root.querySelector(".branch-switcher-btn");
  var nameEl = root.querySelector(".branch-switcher-name");
  var warnEl = root.querySelector(".branch-switcher-warn");
  var menu = root.querySelector(".branch-switcher-menu");
  var userId = root.getAttribute("data-user");
  var branches = [];
  var current = null;

  function read() {
    try {
      var data = JSON.parse(localStorage.getItem(KEY));
      return data && String(data.user) === userId
        ? { id: data.id, name: data.name }
        : null;
    } catch (e) {
      return null;
    }
  }

  function write(branch) {
    try {
      localStorage.setItem(
        KEY,
        JSON.stringify({ id: branch.id, name: branch.name, user: userId }),
      );
    } catch (e) {}
  }

  function clearStored() {
    try {
      localStorage.removeItem(KEY);
    } catch (e) {}
  }

  function notify() {
    document.dispatchEvent(
      new CustomEvent("branchchange", { detail: current }),
    );
  }

  function render() {
    nameEl.textContent = current ? current.name : "Loading…";
    nameEl.title = current ? current.name : "";
    warnEl.hidden = !current || current.id === DEFAULT_ID;
  }

  function setOpen(open) {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function buildMenu() {
    menu.innerHTML = "";
    branches.forEach(function (b) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");

      var item = document.createElement("button");
      item.type = "button";
      item.textContent = b.name;
      item.title = b.name;

      if (current && b.id === current.id) {
        item.className = "selected";
        li.setAttribute("aria-selected", "true");
      }

      item.addEventListener("click", function () {
        var changed = !current || b.id !== current.id;
        current = { id: b.id, name: b.name };
        write(current);
        render();
        buildMenu();
        setOpen(false);
        if (changed) notify();
      });

      li.appendChild(item);
      menu.appendChild(li);
    });
  }

  window.LGSBranch = {
    get: function () {
      return current;
    },
    id: function () {
      return current ? current.id : DEFAULT_ID;
    },
  };

  current = read();
  render();

  fetch(root.getAttribute("data-url"), { credentials: "same-origin" })
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      branches = data.branches || [];
      if (!branches.length) return;

      var defaultId = data.default_id || DEFAULT_ID;
      var match = current
        ? branches.find(function (b) {
            return b.id === current.id;
          })
        : null;
      var fallback =
        branches.find(function (b) {
          return b.id === defaultId;
        }) || branches[0];

      var changed = !current || !match || match.name !== current.name;

      current = match || fallback;
      write(current);
      render();
      buildMenu();
      if (changed) notify();
    })
    .catch(function () {
      if (!current) nameEl.textContent = "Select branch";
    });

  btn.addEventListener("click", function () {
    setOpen(menu.hidden);
  });

  document.addEventListener("click", function (e) {
    if (!root.contains(e.target)) setOpen(false);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setOpen(false);
  });

  window.addEventListener("storage", function (e) {
    if (e.key !== KEY) return;
    current = read();
    render();
    buildMenu();
    if (current) notify();
  });

  var logoutForm = document.querySelector(".app-logout-form");
  if (logoutForm) logoutForm.addEventListener("submit", clearStored);
})();
