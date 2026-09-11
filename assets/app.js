(function () {
  "use strict";

  /* ---------------- language ---------------- */
  var LANG_KEY = "zc-lang";
  var root = document.documentElement;
  var langButtons = document.querySelectorAll("[data-setlang]");

  function applyLang(lang) {
    root.setAttribute("lang", lang);
    langButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.setlang === lang));
    });
    try { localStorage.setItem(LANG_KEY, lang); } catch (e) {}
  }

  var saved = null;
  try { saved = localStorage.getItem(LANG_KEY); } catch (e) {}
  if (saved !== "ko" && saved !== "en") {
    saved = (navigator.language || "").toLowerCase().indexOf("ko") === 0 ? "ko" : "en";
  }
  applyLang(saved);
  langButtons.forEach(function (b) {
    b.addEventListener("click", function () { applyLang(b.dataset.setlang); });
  });

  /* ---------------- scroll reveal ---------------- */
  var revealables = document.querySelectorAll(".rv");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("in");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -12% 0px", threshold: 0.06 });
    revealables.forEach(function (el) { io.observe(el); });
  } else {
    revealables.forEach(function (el) { el.classList.add("in"); });
  }

  function revealWithin(container) {
    container.querySelectorAll(".rv").forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------------- views: home <-> project detail ---------------- */
  var homeView = document.getElementById("home");
  var details = Array.prototype.slice.call(document.querySelectorAll("[data-detail]"));
  var nav = document.querySelector(".nav");

  function showHome(scrollToProjects) {
    details.forEach(function (d) { d.hidden = true; });
    homeView.hidden = false;
    if (nav) nav.hidden = false;
    if (scrollToProjects) {
      var target = document.getElementById("projects");
      if (target) target.scrollIntoView({ behavior: "auto", block: "start" });
    } else {
      window.scrollTo(0, 0);
    }
  }

  function showDetail(id) {
    var panel = document.querySelector('[data-detail="' + id + '"]');
    if (!panel) { showHome(false); return; }
    homeView.hidden = true;
    details.forEach(function (d) { d.hidden = d !== panel; });
    revealWithin(panel);
    window.scrollTo(0, 0);
  }

  function routeFromHash() {
    var hash = (location.hash || "").replace("#", "");
    if (hash.indexOf("project/") === 0) {
      showDetail(hash.slice("project/".length));
    } else {
      details.forEach(function (d) { d.hidden = true; });
      homeView.hidden = false;
    }
  }

  document.querySelectorAll("[data-open]").forEach(function (card) {
    function open() { location.hash = "project/" + card.dataset.open; }
    card.addEventListener("click", open);
    card.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        open();
      }
    });
  });

  document.querySelectorAll("[data-home]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (location.hash) {
        history.replaceState(null, "", location.pathname + location.search);
      }
      showHome(false);
    });
  });

  document.querySelectorAll("[data-back]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (location.hash.indexOf("#project/") === 0) {
        history.replaceState(null, "", location.pathname + location.search);
      }
      showHome(true);
    });
  });

  window.addEventListener("hashchange", routeFromHash);
  routeFromHash();

  /* ---------------- nav: active section ---------------- */
  var navLinks = Array.prototype.slice.call(document.querySelectorAll(".nav__links a"));
  var sections = navLinks
    .map(function (a) { return document.querySelector(a.getAttribute("href")); })
    .filter(Boolean);

  function syncNav() {
    if (homeView.hidden) {
      navLinks.forEach(function (a) { a.classList.remove("active"); });
      return;
    }
    var line = window.scrollY + 140;
    var current = null;
    sections.forEach(function (sec) {
      if (sec.offsetTop <= line) current = sec.id;
    });
    navLinks.forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("href") === "#" + current);
    });
  }

  var ticking = false;
  window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () { syncNav(); ticking = false; });
  }, { passive: true });
  syncNav();

  /* ---------------- year ---------------- */
  var yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());
})();
