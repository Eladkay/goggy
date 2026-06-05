// Dark-mode toggle. Pre-paint script in <head> already applied the saved theme;
// this only wires the toggle button.
(function () {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", function () {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem("goggy-theme", next);
    } catch (e) {}
  });
})();
