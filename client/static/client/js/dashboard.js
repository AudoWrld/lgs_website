document.addEventListener("DOMContentLoaded", function () {
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

  var host = document.getElementById("dash-graph");
  var tip = document.getElementById("dash-graph-tip");
  if (!host || !tip) return;

  var items = Array.prototype.slice.call(
    document.querySelectorAll(".dash-graph-data li"),
  );
  var labels = items.map(function (li) {
    return li.getAttribute("data-label");
  });
  var counts = items.map(function (li) {
    return parseInt(li.getAttribute("data-count"), 10) || 0;
  });
  if (!counts.length) return;

  var NS = "http://www.w3.org/2000/svg";
  var styles = getComputedStyle(document.documentElement);
  var navy = styles.getPropertyValue("--navy").trim() || "#123e5b";
  var orange = styles.getPropertyValue("--orange").trim() || "#f39a2b";

  function make(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    if (parent) parent.appendChild(node);
    return node;
  }

  function draw() {
    var old = host.querySelector("svg");
    if (old) host.removeChild(old);

    var W = host.clientWidth;
    var H = host.clientHeight;
    if (!W || !H) return;

    var pad = { t: 14, r: 16, b: 28, l: 32 };
    var iw = W - pad.l - pad.r;
    var ih = H - pad.t - pad.b;
    var n = counts.length;
    var peak = Math.max.apply(null, counts);
    var step = Math.max(1, Math.ceil(Math.max(3, peak) / 4));
    var top = step * 4;

    function px(i) {
      return n === 1 ? pad.l + iw / 2 : pad.l + (iw * i) / (n - 1);
    }

    function py(v) {
      return pad.t + ih - (v / top) * ih;
    }

    var svg = make(
      "svg",
      { viewBox: "0 0 " + W + " " + H, width: W, height: H },
      host,
    );

    var defs = make("defs", {}, svg);
    var grad = make(
      "linearGradient",
      { id: "dash-graph-fill", x1: "0", y1: "0", x2: "0", y2: "1" },
      defs,
    );
    make(
      "stop",
      { offset: "0", "stop-color": navy, "stop-opacity": "0.26" },
      grad,
    );
    make(
      "stop",
      { offset: "1", "stop-color": navy, "stop-opacity": "0" },
      grad,
    );

    for (var g = 0; g <= 4; g++) {
      var gy = py(g * step);
      make(
        "line",
        {
          x1: pad.l,
          x2: W - pad.r,
          y1: gy,
          y2: gy,
          stroke: "#eee9dd",
          "stroke-width": "1",
        },
        svg,
      );
      var yl = make(
        "text",
        {
          x: pad.l - 8,
          y: gy + 4,
          "text-anchor": "end",
          fill: "#7b858c",
          "font-size": "11",
        },
        svg,
      );
      yl.textContent = g * step;
    }

    for (var i = 0; i < n; i++) {
      var xl = make(
        "text",
        {
          x: px(i),
          y: H - 8,
          "text-anchor": "middle",
          fill: "#7b858c",
          "font-size": "11",
        },
        svg,
      );
      xl.textContent = labels[i];
    }

    var line = "M " + px(0) + " " + py(counts[0]);
    for (var j = 1; j < n; j++) {
      var mx = (px(j - 1) + px(j)) / 2;
      line +=
        " C " +
        mx +
        " " +
        py(counts[j - 1]) +
        " " +
        mx +
        " " +
        py(counts[j]) +
        " " +
        px(j) +
        " " +
        py(counts[j]);
    }

    var base = py(0);
    make(
      "path",
      {
        d:
          line +
          " L " +
          px(n - 1) +
          " " +
          base +
          " L " +
          px(0) +
          " " +
          base +
          " Z",
        fill: "url(#dash-graph-fill)",
      },
      svg,
    );
    make(
      "path",
      {
        d: line,
        fill: "none",
        stroke: navy,
        "stroke-width": "2.5",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      },
      svg,
    );

    var guide = make(
      "line",
      {
        x1: 0,
        x2: 0,
        y1: pad.t,
        y2: pad.t + ih,
        stroke: navy,
        "stroke-opacity": "0.25",
        "stroke-width": "1",
        display: "none",
      },
      svg,
    );

    var dots = [];
    for (var k = 0; k < n; k++) {
      var last = k === n - 1;
      dots.push(
        make(
          "circle",
          {
            cx: px(k),
            cy: py(counts[k]),
            r: last ? 6 : 3.5,
            fill: last ? orange : "#ffffff",
            stroke: last ? "#ffffff" : navy,
            "stroke-width": "2",
          },
          svg,
        ),
      );
    }

    var overlay = make(
      "rect",
      { x: 0, y: 0, width: W, height: H, fill: "transparent" },
      svg,
    );

    function reset() {
      guide.setAttribute("display", "none");
      tip.style.display = "none";
      for (var d = 0; d < dots.length; d++) {
        dots[d].setAttribute("r", d === n - 1 ? 6 : 3.5);
      }
    }

    function show(evt) {
      var rect = host.getBoundingClientRect();
      var point = evt.touches ? evt.touches[0] : evt;
      var x = point.clientX - rect.left;
      var best = 0;
      for (var m = 1; m < n; m++) {
        if (Math.abs(px(m) - x) < Math.abs(px(best) - x)) best = m;
      }

      reset();
      guide.setAttribute("x1", px(best));
      guide.setAttribute("x2", px(best));
      guide.setAttribute("display", "block");
      dots[best].setAttribute("r", 7);

      var count = counts[best];
      tip.textContent =
        labels[best] +
        " · " +
        count +
        (count === 1 ? " certificate" : " certificates");
      tip.style.display = "block";
      tip.style.left = Math.min(Math.max(px(best), 60), W - 60) + "px";
      tip.style.top = Math.max(py(count) - 12, 24) + "px";
    }

    overlay.addEventListener("mousemove", show);
    overlay.addEventListener("touchstart", show, { passive: true });
    overlay.addEventListener("touchmove", show, { passive: true });
    overlay.addEventListener("mouseleave", reset);
    overlay.addEventListener("touchend", reset);
  }

  draw();

  var timer;
  window.addEventListener("resize", function () {
    clearTimeout(timer);
    timer = setTimeout(draw, 120);
  });
});
