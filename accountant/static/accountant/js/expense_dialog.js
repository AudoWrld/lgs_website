(function () {
  var dialog = document.getElementById("ef-submit-dialog");
  var trigger = document.querySelector("[data-confirm-submit]");
  if (!dialog || !trigger || typeof dialog.showModal !== "function") return;

  var form = trigger.closest("form");
  var cancel = dialog.querySelector("[data-dialog-cancel]");
  var confirm = dialog.querySelector("[data-dialog-confirm]");
  var sending = false;

  trigger.addEventListener("click", function (event) {
    if (sending) return;
    event.preventDefault();
    dialog.showModal();
  });

  cancel.addEventListener("click", function () {
    dialog.close();
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });

  confirm.addEventListener("click", function () {
    if (sending) return;
    sending = true;
    confirm.classList.add("is-loading");
    cancel.disabled = true;
    trigger.classList.add("is-loading");
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit(trigger);
    } else {
      var field = document.createElement("input");
      field.type = "hidden";
      field.name = trigger.name;
      field.value = trigger.value;
      form.appendChild(field);
      form.submit();
    }
  });
})();
