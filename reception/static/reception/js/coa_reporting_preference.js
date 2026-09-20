document.addEventListener("DOMContentLoaded", function () {
  var list = document.querySelector("[data-coa-list]");
  if (!list) return;

  var boxes = Array.prototype.slice.call(
    list.querySelectorAll('input[type="checkbox"]'),
  );
  var counter = document.querySelector("[data-coa-selected]");
  var next = document.querySelector("[data-coa-next]");
  var selectAll = document.querySelector("[data-coa-all]");
  var clear = document.querySelector("[data-coa-clear]");

  function sync() {
    var count = boxes.filter(function (box) {
      return box.checked;
    }).length;
    counter.textContent = count + " selected";
    counter.classList.toggle("has-selection", count > 0);
    next.disabled = count === 0;
    selectAll.disabled = count === boxes.length;
    clear.disabled = count === 0;
  }

  boxes.forEach(function (box) {
    box.addEventListener("change", sync);
  });

  selectAll.addEventListener("click", function () {
    boxes.forEach(function (box) {
      box.checked = true;
    });
    sync();
  });

  clear.addEventListener("click", function () {
    boxes.forEach(function (box) {
      box.checked = false;
    });
    sync();
  });

  sync();
});
