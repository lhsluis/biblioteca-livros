const searchInput = document.getElementById("search");
const rows = Array.from(document.querySelectorAll(".row"));
const emptyState = document.getElementById("empty-state");

function normalize(str) {
  return str.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

if (searchInput) {
  searchInput.addEventListener("input", () => {
    const query = normalize(searchInput.value.trim().toLowerCase());
    let anyVisible = false;

    rows.forEach((row) => {
      const cards = Array.from(row.querySelectorAll(".book-card"));
      let rowHasMatch = false;

      cards.forEach((card) => {
        const title = normalize(card.dataset.title || "");
        const author = normalize(card.dataset.author || "");
        const matches = !query || title.includes(query) || author.includes(query);
        card.style.display = matches ? "" : "none";
        if (matches) rowHasMatch = true;
      });

      row.hidden = !rowHasMatch;
      if (rowHasMatch) anyVisible = true;
    });

    if (emptyState) emptyState.hidden = anyVisible;
  });
}
const rescanBtn = document.getElementById("rescan-btn");
if (rescanBtn) {
  rescanBtn.addEventListener("click", async () => {
    rescanBtn.disabled = true;
    const originalText = rescanBtn.textContent;
    rescanBtn.textContent = "Atualizando…";

    try {
      const res = await fetch("/rescan", { method: "POST" });
      if (res.ok) {
        window.location.reload();
        return; // mantém o botão desabilitado até a página recarregar
      }
      throw new Error("Falha ao atualizar");
    } catch (err) {
      rescanBtn.textContent = "Erro ao atualizar";
      setTimeout(() => {
        rescanBtn.textContent = originalText;
        rescanBtn.disabled = false;
      }, 2500);
    }
  });
}

const backToTop = document.getElementById("back-to-top");
if (backToTop) {
  const toggleBackToTop = () => {
    backToTop.classList.toggle("visible", window.scrollY > 280);
  };

  window.addEventListener("scroll", toggleBackToTop, { passive: true });
  toggleBackToTop();

  backToTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}