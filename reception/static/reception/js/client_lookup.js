document.addEventListener("DOMContentLoaded", function () {
  var form = document.querySelector(".sc-search-form");
  if (!form) return;

  var input = form.querySelector(".sc-input-wrap input");
  if (!input) return;

  if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  document.addEventListener("keydown", function (event) {
    var tag = (event.target.tagName || "").toLowerCase();
    var typing =
      tag === "input" ||
      tag === "textarea" ||
      tag === "select" ||
      event.target.isContentEditable;
    if (
      event.key === "/" &&
      !typing &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.altKey
    ) {
      event.preventDefault();
      input.focus();
      input.select();
    }
    if (event.key === "Escape" && event.target === input) input.blur();
  });

  var busy = false;
  var button = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", function (event) {
    if (busy) {
      event.preventDefault();
      return;
    }
    busy = true;
    if (button) button.classList.add("is-loading");
  });

  window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
      busy = false;
      if (button) button.classList.remove("is-loading");
    }
  });
});
