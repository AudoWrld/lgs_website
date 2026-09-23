/**
 * Metallurgical Test Linking (Sample Registration + Sample Edit modal).
 *
 * Wires up, within `root` (document, or the modal body once its HTML is
 * injected):
 *   1. Showing/hiding the Leaching Parameters / Optimization Parameters
 *      sections based on which service checkboxes are ticked (matched via
 *      each checkbox's data-metallurgical-type attribute — see
 *      ServiceCheckboxSelectMultiple in samples/forms.py).
 *   2. "Add Another Parameter" — dynamically adds a text input for a
 *      custom parameter name (e.g. "Sodium Metabisulphite").
 *   3. Packing those custom text inputs into the hidden JSON field
 *      (leaching_custom_parameters / optimization_custom_parameters)
 *      right before the form submits, since Django reads that as one
 *      value rather than a variable number of fields.
 *
 * Call window.initMetallurgicalLinking(root) once per root element:
 *  - on DOMContentLoaded for the main page
 *  - again after the edit modal's HTML is injected
 */
(function () {
  var SECTIONS = [
    {
      type: "CYANIDE_CONVENTIONAL",
      section: ".rc-leaching-section",
      hidden: "[data-role='leaching-custom-json']",
    },
    {
      type: "CYANIDE_OPTIMIZATION",
      section: ".rc-optimization-section",
      hidden: "[data-role='optimization-custom-json']",
    },
  ];

  function isChecked(root, type) {
    var selector = 'input[data-metallurgical-type="' + type + '"]:checked';
    return !!root.querySelector(selector);
  }

  function syncVisibility(root) {
    SECTIONS.forEach(function (cfg) {
      var section = root.querySelector(cfg.section);
      if (!section) return;
      section.style.display = isChecked(root, cfg.type) ? "" : "none";
    });
  }

  function addCustomRow(list, value) {
    var row = document.createElement("div");
    row.className = "rc-custom-param-row";

    var input = document.createElement("input");
    input.type = "text";
    input.className = "rc-custom-param-input";
    input.placeholder = "e.g. Sodium Metabisulphite";
    input.value = value || "";
    input.autocomplete = "off";

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "rc-custom-param-remove";
    remove.setAttribute("aria-label", "Remove parameter");
    remove.innerHTML = "<i class='bx bx-x'></i>";
    remove.addEventListener("click", function () {
      row.remove();
    });

    row.appendChild(input);
    row.appendChild(remove);
    list.appendChild(row);
    return input;
  }

  function collectCustomValues(section) {
    var inputs = section.querySelectorAll(".rc-custom-param-input");
    var values = [];
    inputs.forEach(function (input) {
      var value = input.value.trim();
      if (value) values.push(value);
    });
    return values;
  }

  function packHiddenFields(root) {
    SECTIONS.forEach(function (cfg) {
      var section = root.querySelector(cfg.section);
      var hidden = root.querySelector(cfg.hidden);
      if (!section || !hidden) return;
      hidden.value = JSON.stringify(collectCustomValues(section));
    });
  }

  window.initMetallurgicalLinking = function (root) {
    root = root || document;

    // 1. Show/hide sections when a service checkbox changes.
    root
      .querySelectorAll("input[data-metallurgical-type]")
      .forEach(function (checkbox) {
        checkbox.addEventListener("change", function () {
          syncVisibility(root);
        });
      });
    syncVisibility(root);

    // 2. "Add Another Parameter" buttons.
    root.querySelectorAll(".rc-add-custom-param").forEach(function (button) {
      button.addEventListener("click", function () {
        var section = button.closest(
          ".rc-leaching-section, .rc-optimization-section",
        );
        if (!section) return;
        var list = section.querySelector(".rc-custom-param-list");
        if (!list) return;
        var input = addCustomRow(list, "");
        input.focus();
      });
    });

    // 3. Rehydrate existing custom parameters on edit (initial hidden value).
    SECTIONS.forEach(function (cfg) {
      var section = root.querySelector(cfg.section);
      var hidden = root.querySelector(cfg.hidden);
      if (!section || !hidden || !hidden.value) return;
      var list = section.querySelector(".rc-custom-param-list");
      if (!list || list.children.length) return; // already rendered server-side, skip
      try {
        var values = JSON.parse(hidden.value);
        if (Array.isArray(values)) {
          values.forEach(function (value) {
            addCustomRow(list, value);
          });
        }
      } catch (err) {
        /* ignore malformed initial value */
      }
    });

    // 4. Pack custom inputs into the hidden field right before submit.
    var form = root.closest ? root.closest("form") : null;
    if (!form && root.querySelector) form = root.querySelector("form.rc-form");
    if (form && !form.dataset.metallurgicalBound) {
      form.dataset.metallurgicalBound = "1";
      form.addEventListener("submit", function () {
        packHiddenFields(root);
      });
    }
  };
})();
