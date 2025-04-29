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

