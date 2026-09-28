/* OSO Organised — tiny progressive enhancement only.
   Mobile nav toggle + carousel controls. No libraries, no frameworks. */
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

/* Carousel: works for any .carousel on the page — arrows scroll one slide,
   dots jump to a slide, both stay in sync with manual swipe/scroll. */
(function () {
  var carousels = document.querySelectorAll(".carousel");
  if (!carousels.length) return;

  carousels.forEach(function (carousel) {
    var track = carousel.querySelector(".carousel__track");
    if (!track) return;
    var slides = Array.prototype.slice.call(track.children);
    var prevBtn = carousel.querySelector(".carousel__btn--prev");
    var nextBtn = carousel.querySelector(".carousel__btn--next");
    var dots = Array.prototype.slice.call(carousel.querySelectorAll(".carousel__dot"));

    function currentIndex() {
      var pos = track.scrollLeft;
      var closest = 0, closestGap = Infinity;
      slides.forEach(function (slide, i) {
        var gap = Math.abs(slide.offsetLeft - pos);
        if (gap < closestGap) { closestGap = gap; closest = i; }
      });
      return closest;
    }

    function goTo(i) {
      i = Math.max(0, Math.min(slides.length - 1, i));
      track.scrollTo({ left: slides[i].offsetLeft, behavior: "smooth" });
    }

    function refresh() {
      var i = currentIndex();
      dots.forEach(function (dot, di) {
        dot.setAttribute("aria-current", di === i ? "true" : "false");
      });
      if (prevBtn) prevBtn.disabled = i === 0;
      if (nextBtn) nextBtn.disabled = i === slides.length - 1;
    }

    if (prevBtn) prevBtn.addEventListener("click", function () { goTo(currentIndex() - 1); });
    if (nextBtn) nextBtn.addEventListener("click", function () { goTo(currentIndex() + 1); });
    dots.forEach(function (dot, i) {
      dot.addEventListener("click", function () { goTo(i); });
    });

    var scrollTimer;
    track.addEventListener("scroll", function () {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(refresh, 100);
    });
    window.addEventListener("resize", refresh);

    refresh();
  });
})();
