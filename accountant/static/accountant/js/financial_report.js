(function () {
  var modal = document.getElementById("fm-modal");
  if (!modal || typeof modal.showModal !== "function") return;

  var fromInput = document.getElementById("fm-from");
  var toInput = document.getElementById("fm-to");
  var preview = document.getElementById("fm-preview");
  var pdfLink = document.getElementById("fm-pdf");
  var previewUrl = modal.getAttribute("data-preview-url");
  var pdfUrl = modal.getAttribute("data-pdf-url");
  var placeholder = preview.innerHTML;
  var isoPattern = /^\d{4}-\d{2}-\d{2}$/;
  var controller = null;
  var fromPicker = null;
  var toPicker = null;

  function disableLink() {
    pdfLink.removeAttribute("href");
    pdfLink.setAttribute("aria-disabled", "true");
  }

  function enableLink(query) {
    pdfLink.setAttribute("href", pdfUrl + "?" + query);
    pdfLink.setAttribute("aria-disabled", "false");
  }

  function showNote(text) {
    var note = document.createElement("p");
    note.className = "fm-note";
    note.textContent = text;
    preview.innerHTML = "";
    preview.appendChild(note);
  }

  function stopRequest() {
    if (controller) {
      controller.abort();
      controller = null;
    }
    preview.classList.remove("is-loading");
  }

  function refresh() {
    var from = fromInput.value;
    var to = toInput.value;

    stopRequest();

    if (!isoPattern.test(from) || !isoPattern.test(to)) {
      disableLink();
      preview.innerHTML = placeholder;
      return;
    }

    if (from > to) {
      disableLink();
      showNote("The end date cannot be before the start date.");
      return;
    }

    var query = new URLSearchParams({ from: from, to: to }).toString();
    enableLink(query);

    var current = new AbortController();
    controller = current;
    preview.classList.add("is-loading");

    fetch(previewUrl + "?" + query, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      signal: current.signal,
    })
      .then(function (response) {
        if (!response.ok) throw new Error("preview");
        return response.text();
      })
      .then(function (html) {
        preview.innerHTML = html;
      })
      .catch(function (error) {
        if (error && error.name === "AbortError") return;
        showNote(
          "The preview could not be loaded. You can still print the PDF.",
        );
      })
      .then(function () {
        if (controller === current) {
          controller = null;
          preview.classList.remove("is-loading");
        }
      });
  }

  function buildPickers() {
    var base = {
      dateFormat: "Y-m-d",
      altInput: true,
      altFormat: "j M Y",
      static: true,
      disableMobile: true,
    };

    fromPicker = flatpickr(
      fromInput,
      Object.assign({}, base, {
        onChange: function (dates) {
          toPicker.set("minDate", dates[0] || undefined);
          refresh();
        },
      }),
    );

    toPicker = flatpickr(
      toInput,
      Object.assign({}, base, {
        onChange: function (dates) {
          fromPicker.set("maxDate", dates[0] || undefined);
          refresh();
        },
      }),
    );
  }

  function buildFallback() {
    [fromInput, toInput].forEach(function (input) {
      input.type = "date";
      input.readOnly = false;
      input.addEventListener("change", refresh);
    });
  }

  function reset() {
    if (fromPicker && toPicker) {
      fromPicker.clear(false);
      toPicker.clear(false);
      fromPicker.set("maxDate", undefined);
      toPicker.set("minDate", undefined);
    } else {
      fromInput.value = "";
      toInput.value = "";
    }
    refresh();
  }

  if (typeof flatpickr === "function") {
    buildPickers();
  } else {
    buildFallback();
  }

  disableLink();

  document.querySelectorAll("[data-fm-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      reset();
      modal.showModal();
    });
  });

  modal.querySelectorAll("[data-fm-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      modal.close();
    });
  });

  modal.addEventListener("click", function (event) {
    if (event.target === modal) modal.close();
  });

  modal.addEventListener("close", stopRequest);

  pdfLink.addEventListener("click", function (event) {
    if (pdfLink.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
    }
  });
})();
