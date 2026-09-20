(function () {
  var form = document.querySelector(".rc-form");
  if (!form) return;

  var category = form.elements.category;
  var otherField = document.getElementById("other-category-field");
  var otherInput = form.elements.other_category;

  function syncOtherCategory() {
    var isOther = category.value === "OTHER";
    otherField.hidden = !isOther;
    otherInput.required = isOther;
    if (!isOther) otherInput.value = "";
  }

  if (category && otherField && otherInput) {
    category.addEventListener("change", syncOtherCategory);
    syncOtherCategory();
  }

  form.querySelectorAll(".rc-field.has-error").forEach(function (field) {
    var control = field.querySelector("input, select, textarea");
    var error = field.querySelector(".rc-field-error");
    if (!control) return;
    control.setAttribute("aria-invalid", "true");
    if (error && error.id) control.setAttribute("aria-describedby", error.id);
  });

  var firstInvalid = form.querySelector('[aria-invalid="true"]');
  if (firstInvalid && !firstInvalid.closest("[hidden]")) firstInvalid.focus();

  var submitting = false;
  var buttons = form.querySelectorAll('button[type="submit"]');

  function setBusy(busy) {
    submitting = busy;
    buttons.forEach(function (button) {
      button.classList.toggle("is-loading", busy);
      if (busy) button.setAttribute("aria-disabled", "true");
      else button.removeAttribute("aria-disabled");
    });
  }

  form.addEventListener("submit", function (event) {
    if (submitting) {
      event.preventDefault();
      return;
    }
    setBusy(true);
  });

  window.addEventListener("pageshow", function (event) {
    if (event.persisted) setBusy(false);
  });

  var confirmButton = form.querySelector("[data-confirm-submit]");
  var dialog = document.getElementById("submit-dialog");
  if (!confirmButton) return;

  var hasDialog = dialog && typeof dialog.showModal === "function";

  confirmButton.addEventListener("click", function (event) {
    if (submitting || !form.checkValidity()) return;
    event.preventDefault();
    if (hasDialog) {
      dialog.showModal();
    } else if (
      window.confirm(
        "Submit this expense? You will not be able to view, edit, or access it again after submitting.",
      )
    ) {
      form.requestSubmit(confirmButton);
    }
  });

  if (!hasDialog) return;

  dialog
    .querySelector("[data-dialog-cancel]")
    .addEventListener("click", function () {
      dialog.close();
    });

  dialog
    .querySelector("[data-dialog-confirm]")
    .addEventListener("click", function () {
      dialog.close();
      form.requestSubmit(confirmButton);
    });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });
})();
