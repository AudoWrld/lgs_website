document.addEventListener("DOMContentLoaded", function () {
  var reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;

  var zone = "Africa/Dar_es_Salaam";
  var offset = 0;
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone: zone });
  } catch (e) {
    zone = "UTC";
    offset = 3 * 60 * 60 * 1000;
  }

  var greetingEl = document.querySelector("[data-greeting]");
  var dateEl = document.querySelector("[data-date]");
  var timeEl = document.querySelector("[data-time]");

  function greetingFor(hour) {
    if (hour >= 5 && hour < 12) return "Good morning";
    if (hour >= 12 && hour < 17) return "Good afternoon";
    return "Good evening";
  }

  function tick() {
    var now = new Date(Date.now() + offset);
    var hour =
      parseInt(
        now.toLocaleTimeString("en-GB", {
          timeZone: zone,
          hour: "2-digit",
          hourCycle: "h23",
        }),
        10,
      ) % 24;

    if (greetingEl) greetingEl.textContent = greetingFor(hour);
    if (dateEl) {
      dateEl.textContent = now.toLocaleDateString("en-GB", {
        timeZone: zone,
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    }
    if (timeEl) {
      timeEl.textContent = now.toLocaleTimeString("en-GB", {
        timeZone: zone,
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      });
    }
  }

  tick();
  setInterval(tick, 15000);

  var canvas = document.getElementById("dash-graph-canvas");
  if (canvas && typeof Chart !== "undefined") {
    var items = Array.prototype.slice.call(
      document.querySelectorAll(".dash-graph-data li"),
    );
    var labels = items.map(function (li) {
      return li.getAttribute("data-label");
    });
    var counts = items.map(function (li) {
      return parseInt(li.getAttribute("data-count"), 10) || 0;
    });
    var lastIndex = counts.length - 1;
    var styles = getComputedStyle(document.documentElement);
    var navy = styles.getPropertyValue("--navy").trim() || "#123e5b";
    var orange = styles.getPropertyValue("--orange").trim() || "#f39a2b";
    var context = canvas.getContext("2d");
    var height = canvas.parentNode.clientHeight || 240;
    var fill = context.createLinearGradient(0, 0, 0, height);
    fill.addColorStop(0, "rgba(18, 62, 91, 0.26)");
    fill.addColorStop(1, "rgba(18, 62, 91, 0)");

    try {
      new Chart(canvas, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Submissions",
              data: counts,
              borderColor: navy,
              borderWidth: 2.5,
              backgroundColor: fill,
              fill: true,
              tension: 0.35,
              pointRadius: function (ctx) {
                return ctx.dataIndex === lastIndex ? 6 : 3.5;
              },
              pointHoverRadius: 7,
              pointBackgroundColor: function (ctx) {
                return ctx.dataIndex === lastIndex ? orange : "#ffffff";
              },
              pointBorderColor: function (ctx) {
                return ctx.dataIndex === lastIndex ? "#ffffff" : navy;
              },
              pointBorderWidth: 2,
            },
          ],
        },
        options: {
          animation: reduceMotion
            ? false
            : { duration: 900, easing: "easeOutCubic" },
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          layout: { padding: { top: 12, right: 8 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: navy,
              padding: 10,
              cornerRadius: 4,
              displayColors: false,
              callbacks: {
                label: function (item) {
                  var n = item.parsed.y;
                  return n + (n === 1 ? " submission" : " submissions");
                },
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              suggestedMax: Math.max(3, Math.max.apply(null, counts)),
              ticks: { precision: 0, maxTicksLimit: 5, color: "#7b858c" },
              grid: { color: "#eee9dd" },
              border: { display: false },
            },
            x: {
              ticks: { color: "#7b858c" },
              grid: { display: false },
              border: { color: "#e2dccd" },
            },
          },
        },
      });
    } catch (e) {}
  }
});
