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
