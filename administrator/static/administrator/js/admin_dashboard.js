(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var node = document.getElementById("dash-chart-data");
    if (!node || typeof Chart === "undefined") return;

    var data = JSON.parse(node.textContent);
    var navy = "#123e5b";
    var orange = "#f39a2b";
    var palette = [navy, orange, "#1e7a4d", "#7c3aed", "#c0392b"];

    function money(value) {
      return "TZS " + Number(value).toLocaleString("en-US");
    }

    function compact(value) {
      if (value >= 1000000) return value / 1000000 + "M";
      if (value >= 1000) return value / 1000 + "K";
      return value;
    }

    var revenue = document.getElementById("dash-revenue-canvas");
    if (revenue) {
      new Chart(revenue, {
        type: "line",
        data: {
          labels: data.labels,
          datasets: [
            {
              label: "Billed",
              data: data.billed,
              borderColor: navy,
              backgroundColor: "rgba(18, 62, 91, 0.08)",
              fill: true,
              tension: 0.35,
              pointRadius: 3,
              pointBackgroundColor: navy,
            },
            {
              label: "Collected",
              data: data.collected,
              borderColor: orange,
              backgroundColor: "rgba(243, 154, 43, 0.08)",
              fill: true,
              tension: 0.35,
              pointRadius: 3,
              pointBackgroundColor: orange,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: {
              position: "bottom",
              labels: { usePointStyle: true, boxWidth: 8 },
            },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  return ctx.dataset.label + ": " + money(ctx.parsed.y);
                },
              },
            },
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
            },
            y: {
              beginAtZero: true,
              ticks: { callback: compact },
            },
          },
        },
      });
    }

    var methods = document.getElementById("dash-methods-canvas");
    if (methods) {
      new Chart(methods, {
        type: "doughnut",
        data: {
          labels: data.methods.labels,
          datasets: [
            {
              data: data.methods.values,
              backgroundColor: palette.slice(0, data.methods.values.length),
              borderWidth: 2,
              borderColor: "#ffffff",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "62%",
          plugins: {
            legend: {
              position: "bottom",
              labels: { usePointStyle: true, boxWidth: 8 },
            },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  return ctx.label + ": " + money(ctx.parsed);
                },
              },
            },
          },
        },
      });
    }
  });
})();
