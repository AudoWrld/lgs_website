document.addEventListener("DOMContentLoaded", function () {
  var reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;

  var canvas = document.getElementById("dash-graph-canvas");
  if (!canvas || typeof Chart === "undefined") return;

  var items = Array.prototype.slice.call(
    document.querySelectorAll(".dash-graph-data li"),
  );
  if (!items.length) return;

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
            label: "Samples",
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
                return n + (n === 1 ? " sample" : " samples");
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
});
