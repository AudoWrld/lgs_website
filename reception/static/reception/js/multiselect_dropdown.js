(function () {
  "use strict";

  var counter = 0;
  var openRoot = null;
  var refreshQueued = false;
  var SEARCH_THRESHOLD = 7;

  function textOf(node) {
    return (node.textContent || "").replace(/\s+/g, " ").trim();
  }

  function make(tag, className) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function boxesOf(root) {
    return Array.prototype.slice.call(
      root._ms.list.querySelectorAll(
        'input[type="checkbox"], input[type="radio"]',
      ),
    );
  }

  function visibleBoxes(root) {
    return boxesOf(root).filter(function (box) {
      var item = box.closest(".rc-checkbox-item");
      return !box.disabled && !(item && item.hidden);
    });
  }

  function labelFor(box) {
    var label = box.closest("label");
    return textOf(label || box.parentNode);
  }

  function refresh(root) {
    var ms = root._ms;
    var names = boxesOf(root)
      .filter(function (box) {
        return box.checked;
      })
      .map(labelFor);
    var value = names.length ? names.join(", ") : ms.placeholder;
    if (ms.value.textContent !== value) ms.value.textContent = value;
    ms.value.classList.toggle("is-placeholder", !names.length);
    ms.value.title = names.length > 1 ? names.join(", ") : "";
    var count = names.length > 1 ? String(names.length) : "";
    if (ms.count.textContent !== count) ms.count.textContent = count;
    ms.count.hidden = !count;
    var status = names.length ? names.length + " selected" : "None selected";
    if (ms.status.textContent !== status) ms.status.textContent = status;
    ms.clear.disabled = !names.length;
  }

  function refreshAll() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".rc-ms"),
      function (root) {
        if (root._ms) refresh(root);
      },
    );
  }

  function queueRefresh() {
    if (refreshQueued) return;
    refreshQueued = true;
    window.requestAnimationFrame(function () {
      refreshQueued = false;
      refreshAll();
    });
  }

  function applyFilter(root) {
    var ms = root._ms;
    var query = ms.search ? ms.search.value.trim().toLowerCase() : "";
    var shown = 0;
    Array.prototype.forEach.call(
      ms.list.querySelectorAll(".rc-checkbox-item"),
      function (item) {
        var hide = query && textOf(item).toLowerCase().indexOf(query) === -1;
        item.hidden = !!hide;
        if (!hide) shown += 1;
      },
    );
    ms.empty.hidden = shown > 0;
  }

  function position(root) {
    var ms = root._ms;
    var rect = ms.trigger.getBoundingClientRect();
    var viewport = window.innerHeight;
    if (!rect.width) {
      close(root, false);
      return;
    }
    var clip = ms.trigger.closest(".rc-form, .rc-modal-dialog");
    if (clip) {
      var clipRect = clip.getBoundingClientRect();
      if (rect.bottom < clipRect.top || rect.top > clipRect.bottom) {
        close(root, false);
        return;
      }
    }
    if (rect.bottom < 0 || rect.top > viewport) {
      close(root, false);
      return;
    }
    var gap = 4;
    var margin = 12;
    var below = viewport - rect.bottom - gap - margin;
    var above = rect.top - gap - margin;
    var up = below < 200 && above > below;
    var maxHeight = Math.max(140, Math.min(320, up ? above : below));
    ms.panel.style.width = rect.width + "px";
    ms.panel.style.left = rect.left + "px";
    ms.panel.style.maxHeight = maxHeight + "px";
    if (up) {
      ms.panel.style.top = "auto";
      ms.panel.style.bottom = viewport - rect.top + gap + "px";
    } else {
      ms.panel.style.bottom = "auto";
      ms.panel.style.top = rect.bottom + gap + "px";
    }
    root.classList.toggle("is-up", up);
  }

  function open(root, viaKeyboard) {
    var ms = root._ms;
    if (openRoot && openRoot !== root) close(openRoot, false);
    ms.panel.hidden = false;
    ms.trigger.setAttribute("aria-expanded", "true");
    root.classList.add("is-open");
    openRoot = root;
    position(root);
    if (!viaKeyboard) return;
    var target =
      ms.search ||
      ms.list.querySelector("input:checked") ||
      ms.list.querySelector("input");
    if (target) target.focus();
  }

  function close(root, restoreFocus) {
    var ms = root._ms;
    if (!ms) return;
    ms.panel.hidden = true;
    ms.trigger.setAttribute("aria-expanded", "false");
    root.classList.remove("is-up");
    root.classList.remove("is-open");
    if (openRoot === root) openRoot = null;
    if (ms.search && ms.search.value) {
      ms.search.value = "";
      applyFilter(root);
    }
    if (restoreFocus) ms.trigger.focus();
  }

  function clearAll(root) {
    if (!root || !root._ms) return;
    boxesOf(root).forEach(function (box) {
      if (!box.checked || box.disabled) return;
      box.checked = false;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    });
    refresh(root);
  }

  function enhance(list) {
    if (list.getAttribute("data-ms-ready")) return;
    list.setAttribute("data-ms-ready", "1");
    counter += 1;

    var labelledBy = list.getAttribute("aria-labelledby") || "";
    var labelNode = labelledBy
      ? document.getElementById(labelledBy.split(/\s+/)[0])
      : null;
    var labelText = labelNode ? textOf(labelNode) : "";
    var placeholder = labelText
      ? "Select " + labelText.toLowerCase()
      : "Select options";

    var root = make("div", "rc-ms");
    var triggerId = "rc-ms-trigger-" + counter;
    var panelId = "rc-ms-panel-" + counter;

    var trigger = make("button", "rc-ms-trigger");
    trigger.type = "button";
    trigger.id = triggerId;
    trigger.setAttribute("aria-haspopup", "true");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", panelId);
    if (labelledBy)
      trigger.setAttribute("aria-labelledby", labelledBy + " " + triggerId);

    var value = make("span", "rc-ms-value is-placeholder");
    var count = make("span", "rc-ms-count");
    count.hidden = true;
    var chevron = make("span", "rc-ms-chevron");
    chevron.setAttribute("aria-hidden", "true");
    trigger.appendChild(value);
    trigger.appendChild(count);
    trigger.appendChild(chevron);

    var panel = make("div", "rc-ms-panel");
    panel.id = panelId;
    panel.hidden = true;
    panel.setAttribute("role", "group");
    if (labelText) panel.setAttribute("aria-label", labelText);

    var search = null;
    var itemCount = list.querySelectorAll(".rc-checkbox-item").length;
    if (itemCount > SEARCH_THRESHOLD) {
      var searchWrap = make("div", "rc-ms-search");
      search = make("input", "rc-ms-search-input");
      search.type = "search";
      search.placeholder = "Search…";
      search.autocomplete = "off";
      search.setAttribute(
        "aria-label",
        labelText ? "Filter " + labelText.toLowerCase() : "Filter options",
      );
      searchWrap.appendChild(search);
      panel.appendChild(searchWrap);
    }

    list.parentNode.insertBefore(root, list);
    panel.appendChild(list);

    var empty = make("p", "rc-ms-empty");
    empty.textContent = "No matches found.";
    empty.hidden = true;
    panel.appendChild(empty);

    var footer = make("div", "rc-ms-footer");
    var status = make("span", "rc-ms-status");
    status.setAttribute("aria-live", "polite");
    var clear = make("button", "rc-ms-clear");
    clear.type = "button";
    clear.textContent = "Clear";
    footer.appendChild(status);
    footer.appendChild(clear);
    panel.appendChild(footer);

    root.appendChild(trigger);
    root.appendChild(panel);

    root._ms = {
      trigger: trigger,
      panel: panel,
      list: list,
      value: value,
      count: count,
      status: status,
      clear: clear,
      search: search,
      empty: empty,
      placeholder: placeholder,
    };

    if (search) {
      search.addEventListener("input", function () {
        applyFilter(root);
      });
    }

    refresh(root);
  }

  function enhanceAll() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".rc-checkbox-list:not([data-ms-ready])"),
      enhance,
    );
    refreshAll();
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.closest) {
      var trigger = target.closest(".rc-ms-trigger");
      if (trigger) {
        var root = trigger.closest(".rc-ms");
        if (root && root._ms) {
          if (openRoot === root) close(root, false);
          else open(root, event.detail === 0);
        }
        return;
      }
      var clear = target.closest(".rc-ms-clear");
      if (clear) {
        clearAll(clear.closest(".rc-ms"));
        return;
      }
    }
    queueRefresh();
  });

  document.addEventListener("change", queueRefresh);

  document.addEventListener("pointerdown", function (event) {
    if (!openRoot) return;
    if (!document.body.contains(openRoot)) {
      openRoot = null;
      return;
    }
    if (!openRoot.contains(event.target)) close(openRoot, false);
  });

  document.addEventListener("focusin", function (event) {
    if (
      openRoot &&
      document.body.contains(openRoot) &&
      !openRoot.contains(event.target)
    ) {
      close(openRoot, false);
    }
  });

  document.addEventListener(
    "keydown",
    function (event) {
      var target = event.target;
      if (!openRoot) {
        var trigger =
          target && target.closest ? target.closest(".rc-ms-trigger") : null;
        if (trigger && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
          event.preventDefault();
          open(trigger.closest(".rc-ms"), true);
        }
        return;
      }
      if (!document.body.contains(openRoot)) {
        openRoot = null;
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close(openRoot, true);
        return;
      }
      if (!openRoot.contains(target)) return;

      var isTrigger = target.closest(".rc-ms-trigger");
      var isClear = target.closest(".rc-ms-clear");

      if (event.key === "Enter" && !isTrigger && !isClear) {
        event.preventDefault();
        close(openRoot, true);
        return;
      }

      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        var ms = openRoot._ms;
        var stops = visibleBoxes(openRoot);
        if (ms.search) stops.unshift(ms.search);
        if (!stops.length) return;
        event.preventDefault();
        var index = stops.indexOf(document.activeElement);
        var next;
        if (index === -1) next = 0;
        else
          next =
            event.key === "ArrowDown"
              ? Math.min(index + 1, stops.length - 1)
              : Math.max(index - 1, 0);
        stops[next].focus();
      }
    },
    true,
  );

  window.addEventListener(
    "scroll",
    function (event) {
      if (!openRoot) return;
      if (!document.body.contains(openRoot)) {
        openRoot = null;
        return;
      }
      if (openRoot.contains(event.target)) return;
      position(openRoot);
    },
    true,
  );

  window.addEventListener("resize", function () {
    if (openRoot && document.body.contains(openRoot)) position(openRoot);
  });

  window.addEventListener("pageshow", queueRefresh);

  var observerQueued = false;
  var observer = new MutationObserver(function (records) {
    var found = false;
    records.forEach(function (record) {
      Array.prototype.forEach.call(record.addedNodes, function (node) {
        if (node.nodeType !== 1) return;
        if (
          (node.matches &&
            node.matches(".rc-checkbox-list:not([data-ms-ready])")) ||
          (node.querySelector &&
            node.querySelector(".rc-checkbox-list:not([data-ms-ready])"))
        ) {
          found = true;
        }
      });
    });
    if (!found || observerQueued) return;
    observerQueued = true;
    window.requestAnimationFrame(function () {
      observerQueued = false;
      enhanceAll();
    });
  });

  function start() {
    enhanceAll();
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", start);
  else start();

  window.initMultiselectDropdowns = enhanceAll;
})();
