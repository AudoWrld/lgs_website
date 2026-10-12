(function () {
  var wrapper = document.getElementById("document-number-field");
  var method = document.getElementById("id_payment_method");
  if (!wrapper || !method) return;

  var input = wrapper.querySelector("input");
  var cash = wrapper.getAttribute("data-cash-value");

  function sync() {
    var needed = method.value !== "" && method.value !== cash;
    wrapper.hidden = !needed;
    if (!needed && input) input.value = "";
  }

  method.addEventListener("change", sync);
  sync();
})();
