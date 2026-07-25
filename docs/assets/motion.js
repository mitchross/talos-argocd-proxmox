/* ---------------------------------------------------------------------------
 * Reveal-on-scroll for docs content.
 *
 * Contract with motion.css: this script is the ONLY thing that adds
 * `body.motion-on`, and the CSS only hides elements while that class is set.
 * So if this file 404s, throws, or the browser lacks IntersectionObserver,
 * every page still renders fully — the failure mode is "no animation", never
 * "blank page".
 *
 * Runs again on every navigation because `navigation.instant` swaps the
 * content node without a page load; Material exposes the `document$`
 * observable that fires on each swap.
 * ------------------------------------------------------------------------ */

(function () {
  "use strict";

  // Block-level things worth revealing. Deliberately excludes paragraphs and
  // list items — animating every line of a 750-line runbook is noise.
  var SELECTOR = [
    "h2",
    "h3",
    ".admonition",
    "details",
    ".md-typeset__table",
    ".dgm",
    "blockquote",
    ".highlight",
  ].join(",");

  var STAGGER_MS = 55;
  var STAGGER_MAX = 3;

  var observer = null;

  function reveal(entries) {
    var step = 0;
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry.isIntersecting) continue;
      // Cascade only within a single batch, so a block of siblings entering
      // together arrives in sequence instead of all at once.
      entry.target.style.transitionDelay =
        Math.min(step++, STAGGER_MAX) * STAGGER_MS + "ms";
      entry.target.classList.add("motion-in");
      observer.unobserve(entry.target);
    }
  }

  function init() {
    var body = document.body;
    if (!body) return;

    if (observer) {
      observer.disconnect();
      observer = null;
    }

    var reduced =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduced || !("IntersectionObserver" in window)) {
      body.classList.remove("motion-on");
      return;
    }

    var content = document.querySelector(".md-content__inner");
    if (!content) {
      body.classList.remove("motion-on");
      return;
    }

    var nodes = content.querySelectorAll(SELECTOR);
    if (!nodes.length) {
      body.classList.remove("motion-on");
      return;
    }

    observer = new IntersectionObserver(reveal, {
      // Trigger slightly before the element is fully on screen so the motion
      // completes about when the reader's eye arrives.
      rootMargin: "0px 0px -6% 0px",
      threshold: 0.01,
    });

    body.classList.add("motion-on");

    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      // Skip anything already inside a tracked ancestor (a code block inside
      // an admonition, a table inside a <details>) — nested reveals stutter.
      if (el.parentElement && el.parentElement.closest("[data-motion]")) {
        continue;
      }
      el.setAttribute("data-motion", "");
      observer.observe(el);
    }
  }

  if (typeof window.document$ !== "undefined" && window.document$.subscribe) {
    window.document$.subscribe(init);
  } else if (document.readyState !== "loading") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
