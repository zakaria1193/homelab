const box = document.getElementById("log");
const stick = document.getElementById("tailtoggle");
function toBottom() { if (stick.checked) box.scrollTop = box.scrollHeight; }
toBottom();

async function reload() {
  const response = await fetch(location.pathname + location.search + "&raw=1",
                               { cache: "no-store" });
  box.textContent = await response.text();
  toBottom();
}
document.getElementById("reload").addEventListener("click", reload);

let timer = null;
document.getElementById("follow").addEventListener("change", (event) => {
  clearInterval(timer);
  if (event.target.checked) timer = setInterval(reload, 5000);
});
