(function () {
  var root = document.querySelector("[data-branch-switcher]");
  if (!root) return;

  var btn = root.querySelector(".branch-switcher-btn");
  var nameEl = root.querySelector(".branch-switcher-name");
  var warnEl = root.querySelector(".branch-switcher-warn");
  var menu = root.querySelector(".branch-switcher-menu");
  var setUrl = root.getAttribute("data-set-url");
  var csrf = root.getAttribute("data-csrf");
  var branches = [];
  var current = null;
  var defaultId = null;
  var busy = false;

  function render() {
    nameEl.textContent = current ? current.name : "Loading…";
    nameEl.title = current ? current.name : "";
    warnEl.hidden = !current || current.id === defaultId;
  }

  function setOpen(open) {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function switchBranch(branch) {
    if (busy) return;
    if (current && branch.id === current.id) {
      setOpen(false);
      return;
    }

    busy = true;
    btn.disabled = true;

    var body = new URLSearchParams();
    body.set("branch_id", branch.id);

    fetch(setUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrf,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("Request failed");
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error("Request failed");
        window.location.reload();
      })
      .catch(function () {
        busy = false;
        btn.disabled = false;
        setOpen(false);
      });
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
        switchBranch(b);
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
      return current ? current.id : defaultId;
    },
  };

  render();

  fetch(root.getAttribute("data-url"), { credentials: "same-origin" })
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      branches = data.branches || [];
      defaultId = data.default_id;
      if (!branches.length) {
        nameEl.textContent = "No branches";
        return;
      }

      current =
        branches.find(function (b) {
          return b.id === data.selected_id;
        }) || branches[0];

      render();
      buildMenu();
    })
    .catch(function () {
      if (!current) nameEl.textContent = "Select branch";
    });

  btn.addEventListener("click", function () {
    if (!busy) setOpen(menu.hidden);
  });

  document.addEventListener("click", function (e) {
    if (!root.contains(e.target)) setOpen(false);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setOpen(false);
  });
})();
