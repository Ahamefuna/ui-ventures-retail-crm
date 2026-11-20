/* Shared navigation, password visibility toggle, and form submit guards */

document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("uivSidebar");
  const backdrop = document.getElementById("uivSidebarBackdrop");
  const toggleBtn = document.getElementById("uivSidebarToggle");

  const closeSidebar = () => {
    if (sidebar) sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("show");
  };

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      const isOpen = sidebar.classList.toggle("open");
      if (backdrop) backdrop.classList.toggle("show", isOpen);
    });
  }

  if (backdrop) {
    backdrop.addEventListener("click", closeSidebar);
  }

  document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-toggle-password");
      const input = document.getElementById(targetId);
      if (!input) return;
      const isPassword = input.type === "password";
      input.type = isPassword ? "text" : "password";
      const icon = btn.querySelector("i");
      if (icon) {
        icon.className = isPassword ? "bi bi-eye-slash" : "bi bi-eye";
      }
    });
  });

  document.querySelectorAll("form[data-loading-text]").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector('button[type="submit"]');
      if (!btn || btn.disabled) return;
      const loadingText = form.getAttribute("data-loading-text");
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${loadingText}`;
    });
  });
});
