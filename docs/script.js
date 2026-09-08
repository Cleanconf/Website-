/* OSO Organised — tiny progressive enhancement only.
   Mobile nav toggle. No libraries, no frameworks. */
(function () {
  var toggle = document.querySelector(".nav-toggle");
  var menu = document.getElementById("nav-menu");
  if (!toggle || !menu) return;

  var mq = window.matchMedia("(max-width: 860px)");

  function setState(open) {
    toggle.setAttribute("aria-expanded", String(open));
    if (mq.matches) {
      menu.hidden = !open;
    } else {
      menu.hidden = false;
    }
  }

  setState(false);
  mq.addEventListener("change", function () { setState(false); });

  toggle.addEventListener("click", function () {
    setState(toggle.getAttribute("aria-expanded") !== "true");
  });

  menu.addEventListener("click", function (e) {
    if (e.target.tagName === "A" && mq.matches) setState(false);
  });
})();
