(function () {
  var greetingEl = document.querySelector("[data-greeting]");
  var dateEl = document.querySelector("[data-date]");
  var timeEl = document.querySelector("[data-time]");

  function nairobiParts() {
    var now = new Date();
    var time = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Africa/Nairobi",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(now);
    var date = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Africa/Nairobi",
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    })
      .format(now)
      .replace(/,/g, "");
    return { hour: parseInt(time.slice(0, 2), 10), time: time, date: date };
  }

  function greetingFor(hour) {
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }

  function update() {
    var parts = nairobiParts();
    if (greetingEl) greetingEl.textContent = greetingFor(parts.hour);
    if (timeEl) timeEl.textContent = parts.time;
    if (dateEl) dateEl.textContent = parts.date;
  }

  update();
  setInterval(update, 30000);
})();
