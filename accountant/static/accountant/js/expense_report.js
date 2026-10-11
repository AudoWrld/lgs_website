document.addEventListener("DOMContentLoaded", function () {
  var dialog = document.getElementById("ex-report-modal");
  var openers = document.querySelectorAll("[data-report-open]");
  if (!dialog || !openers.length) return;

  var fromInput = document.getElementById("ex-report-from");
  var toInput = document.getElementById("ex-report-to");
  var pdfLink = document.getElementById("ex-report-pdf");
  var box = document.getElementById("ex-report-preview");
  var previewUrl = dialog.getAttribute("data-preview-url");
  var pdfUrl = dialog.getAttribute("data-pdf-url");
  var hasPicker = typeof flatpickr !== "undefined";
  var fromPicker = null;
  var toPicker = null;
  var ticket = 0;
  var timer = null;

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function iso(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function read(input, picker) {
    if (picker) return picker.selectedDates.length ? picker.selectedDates[0] : null;
    var parts = (input.value || "").split("-");
    if (parts.length !== 3) return null;
    var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    return isNaN(d.getTime()) ? null : d;
  }

  function say(text) {
    box.innerHTML = "";
    var p = document.createElement("p");
    p.className = "rp-note";
    p.textContent = text;
    box.appendChild(p);
  }

  function setPdf(from, to) {
    if (from && to && from <= to) {
      pdfLink.href = pdfUrl + "?from=" + iso(from) + "&to=" + iso(to);
      pdfLink.removeAttribute("aria-disabled");
    } else {
      pdfLink.removeAttribute("href");
      pdfLink.setAttribute("aria-disabled", "true");
    }
  }

  function refresh() {
    var from = read(fromInput, fromPicker);
    var to = read(toInput, toPicker);
    setPdf(from, to);

    if (!from || !to) {
      say("Choose both dates to see a preview.");
      return;
    }
    if (from > to) {
      say("The start date must be on or before the end date.");
      return;
    }

    var mine = ++ticket;
    box.classList.add("is-loading");
    fetch(previewUrl + "?from=" + iso(from) + "&to=" + iso(to), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error("bad response");
        return response.text();
      })
      .then(function (html) {
        if (mine === ticket) box.innerHTML = html;
      })
      .catch(function () {
        if (mine === ticket) say("The preview could not be loaded. Please try again.");
      })
      .then(function () {
        if (mine === ticket) box.classList.remove("is-loading");
      });
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refresh, 150);
  }

  function setup() {
    if (fromPicker || toPicker) return;

    var now = new Date();
    var first = new Date(now.getFullYear(), now.getMonth(), 1);

    if (!hasPicker) {
      fromInput.type = "date";
      toInput.type = "date";
      fromInput.readOnly = false;
      toInput.readOnly = false;
      fromInput.value = iso(first);
      toInput.value = iso(now);
      fromInput.addEventListener("change", schedule);
      toInput.addEventListener("change", schedule);
      return;
    }

    var common = {
      dateFormat: "d M Y",
      disableMobile: true,
      static: true,
      allowInput: false,
      maxDate: "today",
      locale: { firstDayOfWeek: 1 },
    };

    fromPicker = flatpickr(
      fromInput,
      Object.assign({}, common, {
        defaultDate: first,
        onChange: function (dates) {
          if (dates.length) toPicker.set("minDate", dates[0]);
          schedule();
        },
      }),
    );

    toPicker = flatpickr(
      toInput,
      Object.assign({}, common, {
        defaultDate: now,
        minDate: first,
        onChange: function (dates) {
          if (dates.length) fromPicker.set("maxDate", dates[0]);
          schedule();
        },
      }),
    );

    fromPicker.set("maxDate", now);
  }

  function open() {
    setup();
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    refresh();
  }

  function close() {
    if (typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  }

  Array.prototype.forEach.call(openers, function (button) {
    button.addEventListener("click", open);
  });

  Array.prototype.forEach.call(dialog.querySelectorAll("[data-report-close]"), function (button) {
    button.addEventListener("click", close);
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) close();
  });

  pdfLink.addEventListener("click", function (event) {
    if (pdfLink.getAttribute("aria-disabled") === "true") event.preventDefault();
  });
});