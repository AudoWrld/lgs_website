document.addEventListener("DOMContentLoaded", function () {
  var reduceMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;
  var styles = getComputedStyle(document.documentElement);
  var navy = styles.getPropertyValue("--navy").trim() || "#123e5b";
  var orange = styles.getPropertyValue("--orange").trim() || "#f39a2b";

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    try {
      var value = JSON.parse(el.textContent);
      if (typeof value === "string") value = JSON.parse(value);
      return Array.isArray(value) ? value : [];
    } catch (e) {
      return [];
    }
  }

  if (!reduceMotion) {
    document.querySelectorAll("[data-count]").forEach(function (el) {
      var target = parseInt(el.textContent.replace(/[^0-9]/g, ""), 10);
      if (!isFinite(target) || target < 1) return;
      var duration = 700;
      var start = null;
      el.textContent = "0";
      function tick(now) {
        if (start === null) start = now;
        var progress = Math.min((now - start) / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased).toLocaleString();
        if (progress < 1) requestAnimationFrame(tick);
        else el.textContent = target.toLocaleString();
      }
      requestAnimationFrame(tick);
    });
  }

  var canvas = document.getElementById("rc-weekly-chart");
  if (canvas && typeof Chart !== "undefined") {
    var counts = readJson("rc-week-counts");
    var lastIndex = counts.length - 1;
    try {
      new Chart(canvas, {
        type: "bar",
        data: {
          labels: readJson("rc-week-labels"),
          datasets: [
            {
              label: "Submissions",
              data: counts,
              backgroundColor: function (ctx) {
                return ctx.dataIndex === lastIndex ? orange : navy;
              },
              hoverBackgroundColor: orange,
              borderRadius: 3,
              maxBarThickness: 28,
            },
          ],
        },
        options: {
          animation: reduceMotion
            ? false
            : { duration: 700, easing: "easeOutCubic" },
          responsive: true,
          maintainAspectRatio: false,
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
              ticks: { precision: 0, color: "#7b858c" },
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

  var toolbar = document.querySelector("form[data-autosubmit]");
  if (toolbar) {
    toolbar
      .querySelectorAll('input[type="date"], select')
      .forEach(function (control) {
        control.addEventListener("change", function () {
          toolbar.submit();
        });
      });

    var search = toolbar.querySelector('input[name="q"]');
    if (search) {
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
          search.focus();
          search.select();
        }
        if (event.key === "Escape" && event.target === search) search.blur();
      });
    }
  }
});
