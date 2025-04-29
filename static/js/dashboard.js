const tbody = document.getElementById('orders-table').querySelector('tbody');
const row = document.createElement('tr');
row.innerHTML = `
  <td>${data.time}</td>
  <td style="cursor:pointer;" onclick="openChart('${data.stock}')">${data.stock}</td>
  <td>${data.action}</td>
  <td>${data.qty}</td>
  <td>₹${data.price}</td>
  <td>${data.variety}</td>
`;
tbody.prepend(row);

function openChart(stock) {
  const iframe = document.getElementById('tvChart');
  const chartTitle = document.getElementById('chartTitle');
  chartTitle.textContent = `📊 NSE:${stock} Chart`;
  iframe.src = `https://s.tradingview.com/widgetembed/?symbol=NSE:${stock}&interval=15&theme=dark&style=1`;
  const modal = new bootstrap.Modal(document.getElementById('chartModal'));
  modal.show();
}
function toggleDarkMode() {
  const body = document.getElementById('body');
  const table = document.getElementById('orders-table');

  body.classList.toggle('bg-dark');
  body.classList.toggle('text-white');

  if (table) {
    table.classList.toggle('table-dark');
  }

  document.querySelectorAll('.card').forEach(card => {
    card.classList.toggle('bg-dark');
    card.classList.toggle('text-white');
  });

  document.querySelectorAll('button').forEach(btn => {
    btn.classList.toggle('btn-light');
    btn.classList.toggle('btn-dark');
  });
}
<script>
async function toggleCopyTrading(status) {
  await fetch("/toggle-copy-trading", {
    method: "POST",
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ enabled: status })
  });
  alert("Copy Trading " + (status ? "Enabled" : "Disabled"));
}

async function makeNewMaster() {
  const selected = document.getElementById("new-master").value;
  await fetch(`/make-master/${selected}`, { method: "POST" });
  alert(`✅ ${selected} is now Master. Reloading...`);
  location.reload();
}

async function loadDropdown() {
  const response = await fetch("/config.yaml");
  const text = await response.text();
  const config = jsyaml.load(text);
  const dropdown = document.getElementById("new-master");

  config.child_accounts.forEach(child => {
    const option = document.createElement("option");
    option.value = child.name;
    option.innerText = child.name;
    dropdown.appendChild(option);
  });
}
window.onload = loadDropdown;
</script>

