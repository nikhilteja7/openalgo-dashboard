
function updateZerodhaLoginLink(master) {
  if (master && master.api_key) {
    const loginBtn = document.getElementById("zerodhaLoginBtn");
    if (loginBtn) {
      loginBtn.href = `https://kite.zerodha.com/connect/login?v=3&api_key=${master.api_key}`;
    }
  }
}


// dashboard.js

// Utility to toggle visibility of the add account form
function toggleAddForm() {
  const form = document.getElementById('addAccountForm');
  form.classList.toggle('show');
}

// Load accounts for Account Config section
async function loadAccounts() {
  const res = await fetch('/get-accounts-details');
  const data = await res.json();
  const container = document.getElementById("accounts");
  container.innerHTML = "";
  let netPnlTotal = 0;

  let sortByToday = localStorage.getItem('sortMode') !== 'net';
  const toggleBtn = document.getElementById('sortToggle');
  if (toggleBtn) {
    toggleBtn.innerText = sortByToday ? 'Sort by Net P&L' : "Sort by Today's P&L";
    toggleBtn.dataset.sort = sortByToday ? 'net' : 'today';
    localStorage.setItem('sortMode', sortByToday ? 'today' : 'net');
  }

  const sorted = data.accounts.sort((a, b) => {
    return sortByToday ? b.pnl - a.pnl : (b.balance - b.opening_balance) - (a.balance - a.opening_balance);
  });

  sorted.forEach(acc => {
        if (!acc.status) {
          showToast(`⚠️ Session expired: ${acc.name}`, false);
        }
    netPnlTotal += acc.pnl;
    const card = document.createElement('div');
    const pnlColor = acc.pnl >= 0 ? 'green' : 'red';
    const percent = acc.opening_balance ? ((acc.balance - acc.opening_balance) / acc.opening_balance) * 100 : 0;
    card.className = `card ${pnlColor}`;
    card.innerHTML = `
      <b>${acc.name}</b> ${acc.is_master ? '<span>(Master)</span>' : ''} <br/>
      Status: ${acc.status ? '✅' : '❌'}<br/>
      Opening Balance: ₹${acc.opening_balance.toFixed(2)}<br/>
      Current Balance: ₹${acc.balance.toFixed(2)}<br/>
      Net P&L: <span class="${pnlColor}">₹${(acc.balance - acc.opening_balance).toFixed(2)} (${percent.toFixed(2)}%)</span><br/>
      Today's P&L: <span class="${pnlColor}">₹${acc.pnl.toFixed(2)}</span><br/>
      AutoLogin: <input type="checkbox" onchange="toggleAutoLogin('${acc.name}', this.checked)" ${acc.autologin ? 'checked' : ''}><br/>
      <button onclick="refreshSession('${acc.name}')">Reconnect</button>
      <button onclick="editAccount('${acc.name}')">Edit</button>
      <button onclick="deleteAccount('${acc.name}')">Delete</button>
    `;
    container.appendChild(card);
  });

  const net = document.getElementById('netPnl');
  const color = netPnlTotal >= 0 ? 'green' : 'red';
  net.innerHTML = `Net P&L Today: <span class="${color}">₹${netPnlTotal.toFixed(2)}</span>`;

  // Populate dropdowns for copy trading
  const masterSel = document.getElementById("masterSelect");
  const childSel = document.getElementById("childSelect");
  if (masterSel && childSel) {
    masterSel.innerHTML = "";
    childSel.innerHTML = "";
    data.accounts.forEach(acc => {
      const opt = document.createElement('option');
      opt.value = acc.name;
      opt.text = acc.name;
      if (!acc.is_master) childSel.appendChild(opt);
      else masterSel.appendChild(opt);
    });
  }
}

function addAccount() {
  const name = document.getElementById('clientId').value.trim();
  const api_key = document.getElementById('apiKey').value.trim();
  const api_secret = document.getElementById('apiSecret').value.trim();
  const totp_key = document.getElementById('totpKey').value.trim();
  const email = document.getElementById('emailId').value.trim();
  const mobile = document.getElementById('mobileNo').value.trim();

  if (!name || !api_key || !api_secret || !totp_key) {
    alert("Please fill all required fields.");
    return;
  }

  const data = { name, api_key, api_secret, totp_key, email, mobile };

  fetch('/add-account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).then(res => res.json()).then(response => {
    showToast(response.message, response.status === 'success'); playSoundAlert();
    loadAccounts();
    document.getElementById('addAccountForm').classList.remove('show');
  });
}

function toggleAutoLogin(id, val) {
  fetch('/toggle-autologin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: id, autologin: val })
  });
}

function refreshSession(name) {
  fetch('/refresh-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: name })
  }).then(r => r.json()).then(() => loadAccounts());
}

function deleteAccount(name) {
  if (!confirm("Delete account " + name + "?")) return;
  fetch('/delete-account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: name })
  }).then(() => loadAccounts());
}

function editAccount(clientId) {
  const modal = document.createElement('div');
  modal.style.position = 'fixed';
  modal.style.top = '0';
  modal.style.left = '0';
  modal.style.width = '100%';
  modal.style.height = '100%';
  modal.style.backgroundColor = 'rgba(0,0,0,0.5)';
  modal.style.display = 'flex';
  modal.style.alignItems = 'center';
  modal.style.justifyContent = 'center';

  const form = document.createElement('div');
  form.style.background = '#fff';
  form.style.padding = '20px';
  form.style.borderRadius = '8px';
  form.innerHTML = `
    <h3>Edit Account: ${clientId}</h3>
    <input id="editApiKey" placeholder="New API Key" style="width: 100%; margin: 10px 0;"><br/>
    <input id="editApiSecret" placeholder="New API Secret" style="width: 100%; margin: 10px 0;"><br/>
    <input id="editTotpKey" placeholder="New TOTP Key" style="width: 100%; margin: 10px 0;"><br/>
    <input id="editEmail" placeholder="Email (optional)" style="width: 100%; margin: 10px 0;"><br/>
    <input id="editMobile" placeholder="Mobile (optional)" style="width: 100%; margin: 10px 0;"><br/>
    <button onclick="submitEditAccount('${clientId}')">Save</button>
    <button onclick="this.parentElement.parentElement.remove()">Cancel</button>
  `;
  modal.appendChild(form);
  document.body.appendChild(modal);
}

function submitEditAccount(clientId) {
  const api_key = document.getElementById('editApiKey').value.trim();
  const api_secret = document.getElementById('editApiSecret').value.trim();
  const totp_key = document.getElementById('editTotpKey').value.trim();
  const email = document.getElementById('editEmail').value.trim();
  const mobile = document.getElementById('editMobile').value.trim();

  const data = { client_id: clientId, api_key, api_secret, totp_key, email, mobile };

  fetch('/edit-account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).then(() => {
    loadAccounts();
    document.querySelectorAll('div[style*="rgba(0,0,0"]')[0].remove();
  });
}

// Order row insertion
function appendOrderRow(data) {
  const tbody = document.getElementById('orders-table')?.querySelector('tbody');
  if (!tbody) return;
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
}

// TradingView Chart Modal
function openChart(stock) {
  const iframe = document.getElementById('tvChart');
  const chartTitle = document.getElementById('chartTitle');
  if (chartTitle) chartTitle.textContent = `📊 NSE:${stock} Chart`;
  if (iframe) iframe.src = `https://s.tradingview.com/widgetembed/?symbol=NSE:${stock}&interval=15&theme=dark&style=1`;
  const modal = new bootstrap.Modal(document.getElementById('chartModal'));
  modal.show();
}

// Dark mode toggle and persistence
function toggleDarkMode() {
  const body = document.body;
  const table = document.getElementById('orders-table');
  body.classList.toggle('bg-dark');
  body.classList.toggle('text-white');
  if (table) table.classList.toggle('table-dark');
  document.querySelectorAll('.card').forEach(card => {
    card.classList.toggle('bg-dark');
    card.classList.toggle('text-white');
  });
  document.querySelectorAll('button').forEach(btn => {
    btn.classList.toggle('btn-light');
    btn.classList.toggle('btn-dark');
  });
  localStorage.setItem('darkMode', body.classList.contains('bg-dark'));
}

// Persist dark mode
if (localStorage.getItem('darkMode') === 'true') toggleDarkMode();

// Copy trading controls
async function toggleCopyTrading(status) {
  await fetch("/toggle-copy-trading", {
    method: "POST",
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ enabled: status })
  });
  showToast(`Copy Trading ${status ? 'Enabled' : 'Disabled'}`); playSoundAlert();
}

async function makeNewMaster() {
  const selected = document.getElementById("new-master").value;
  await fetch(`/make-master/${selected}`, { method: "POST" });
  showToast(`✅ ${selected} is now Master`, true); playSoundAlert();
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

// Child Account Rendering
function renderChildAccounts(accounts) {
  const container = document.getElementById("childAccountsContainer");
  if (!container) return;
  container.innerHTML = "";

  accounts.filter(acc => !acc.is_master).forEach(child => {
    const pnlColor = child.pnl >= 0 ? 'green' : 'red';
    const percent = child.opening_balance ? ((child.balance - child.opening_balance) / child.opening_balance) * 100 : 0;

    const card = document.createElement('div');
    card.className = `card ${pnlColor}`;
    card.innerHTML = `
      <h4>Child: ${child.name}</h4>
      Balance: ₹${child.balance.toFixed(2)}<br/>
      Multiplier: <select onchange="setMultiplier('${child.name}', this.value)">
        ${[0.5,1,2,3,4,5,6,7,8,9,10].map(x => `<option value="${x}" ${child.multiplier == x ? 'selected' : ''}>${x}x</option>`).join('')}
      </select><br/>
      Trade: <input type="checkbox" ${child.copy_enabled ? 'checked' : ''} onchange="toggleChildCopy('${child.name}', this.checked)"><br/>
      P&L: ₹${child.pnl.toFixed(2)} | Net: ₹${(child.balance - child.opening_balance).toFixed(2)} (${percent.toFixed(2)}%)<br/>
      <button onclick="toggleOrderConsole('${child.name}')">📘 Orders</button>
      <button onclick="togglePositionConsole('${child.name}')">📊 Positions</button>
      <div id="console-${child.name}" style="display:none;"></div>
      <button onclick="editAccount('${child.name}')">✏️ Edit</button>
      <button onclick="deleteAccount('${child.name}')">🗑️ Delete</button>
      <button onclick="exitAll('${child.name}')">❌ Exit All</button>
    `;
    container.appendChild(card);
  });
}

function setMultiplier(name, value) {
  fetch('/set-multiplier', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ client_id: name, multiplier: parseFloat(value) })
  });
}
function isDuplicateAccount() {
  const name = document.getElementById('clientId').value.trim();
  const existing = Array.from(document.querySelectorAll('#accounts tr td:first-child'))
                        .map(td => td.textContent.trim());
  if (existing.includes(name)) {
    showToast(`🚫 Account '${name}' already exists.`, false);
    return true;
  }
  return false;
}

function logout() {
  if (confirm("Are you sure you want to logout?")) {
    window.location.href = "/logout";
  }
}

function toggleChildCopy(name, status) {
  fetch('/toggle-child-copy', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ client_id: name, enabled: status })
  });
}

// Master + Child render integration
function renderCopyTradingView(data) {
  const master = data.accounts.find(acc => acc.is_master);
  if (!master) return;
  document.getElementById("masterClientId").textContent = `Client ID: ${master.name}`;
  document.getElementById("masterBalance").textContent = master.balance.toFixed(2);
  document.getElementById("masterPnl").textContent = master.pnl.toFixed(2);
  document.getElementById("masterNetPnl").textContent = (master.balance - master.opening_balance).toFixed(2);
  document.getElementById("copyAllToggle").checked = master.copy_enabled;

  renderChildAccounts(data.accounts);

  // Fill master console (order + positions)
  const masterConsole = document.getElementById("masterConsole");
  if (masterConsole) {
    masterConsole.innerHTML = `
      <h5>Order Book</h5>
      <div>${(master.orders || []).map(o => `${o.symbol} - ${o.action} - Qty: ${o.qty}`).join('<br/>') || 'No orders'}</div>
      <h5>Positions</h5>
      <div>${(master.positions || []).map(p => `${p.symbol}: Qty ${p.qty}`).join('<br/>') || 'No positions'}</div>
    `;
  }

  // Fill each child console
  data.accounts.filter(a => !a.is_master).forEach(child => {
    const div = document.getElementById(`console-${child.name}`);
    if (div) {
      div.innerHTML = `
        <h5>Order Book</h5>
        <div>${(child.orders || []).map(o => `${o.symbol} - ${o.action} - Qty: ${o.qty}`).join('<br/>') || 'No orders'}</div>
        <h5>Positions</h5>
        <div>${(child.positions || []).map(p => `${p.symbol}: Qty ${p.qty}`).join('<br/>') || 'No positions'}</div>
      `;
    }
  });
}
}

function toggleOrderConsole(id) {
  const div = document.getElementById(`console-${id}`);
  if (div) div.style.display = div.style.display === 'none' ? 'block' : 'none';
}

function togglePositionConsole(id) {
  const div = document.getElementById(`console-${id}`);
  if (div) div.style.display = div.style.display === 'none' ? 'block' : 'none';
}

// Trade Summary Rendering
// 📌 Insert this inside your HTML under Trade Summary section:
// <table id="tradeSummaryTable">
//   <thead>
//     <tr>
//       <th data-key="name">Client ID</th>
//       <th data-key="live_balance">Live Balance</th>
//       <th data-key="net_pnl">Net P&L</th>
//       <th data-key="total_trades">Total Trades</th>
//       <th data-key="wins">Wins</th>
//       <th data-key="losses">Losses</th>
//       <th data-key="win_rate">Win Rate %</th>
//       <th data-key="top_symbol">Top Symbol</th>
//     </tr>
//   </thead>
//   <tbody id="tradeSummaryBody"></tbody>
// </table>
// <button onclick="downloadTradeSummaryCSV()">📥 Export CSV</button>

// Ensure these headers are added in HTML:
// <th data-key="name">Client ID</th>
// <th data-key="live_balance">Live Balance</th>
// <th data-key="net_pnl">Net P&L</th>
// <th data-key="total_trades">Total Trades</th>
// <th data-key="wins">Wins</th>
// <th data-key="losses">Losses</th>
// <th data-key="win_rate">Win Rate %</th>
// <th data-key="top_symbol">Top Symbol</th>
// And add this button near the table:
// <button onclick="downloadTradeSummaryCSV()">📥 Export CSV</button>
let tradeSummarySort = { key: 'net_pnl', asc: false };

function sortTradeSummary(data) {
  const { key, asc } = tradeSummarySort;
  return data.sort((a, b) => {
    const aVal = a[key] ?? 0;
    const bVal = b[key] ?? 0;
    return asc ? aVal - bVal : bVal - aVal;
  });
}

function downloadTradeSummaryCSV() {
  fetch('/get-accounts-summary')
    .then(res => res.json())
    .then(summary => {
      const rows = [
        ['Client ID', 'Live Balance', 'Net P&L', 'Total Trades', 'Wins', 'Losses', 'Win Rate %', 'Top Symbol']
      ];
      summary.accounts.forEach(acc => {
        rows.push([
          acc.name,
          acc.live_balance?.toFixed(2) || 0,
          acc.net_pnl,
          acc.total_trades,
          acc.wins,
          acc.losses,
          acc.win_rate,
          acc.top_symbol
        ]);
      });
      const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(r => r.join(',')).join('
');
      const link = document.createElement('a');
      link.setAttribute('href', encodeURI(csvContent));
      link.setAttribute('download', 'trade_summary.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
    });
}

function renderTradeSummary() {
  fetch('/get-accounts-summary')
    .then(res => res.json())
    .then(summary => {
      const tbody = document.getElementById('tradeSummaryBody');
      if (!tbody) return;
      tbody.innerHTML = "";
      const header = document.querySelector('#tradeSummaryTable thead');
      if (header && !header.dataset.sorted) {
        header.dataset.sorted = true;
        header.querySelectorAll('th[data-key]').forEach(th => {
          th.style.cursor = 'pointer';
          th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (tradeSummarySort.key === key) {
              tradeSummarySort.asc = !tradeSummarySort.asc;
            } else {
              tradeSummarySort.key = key;
              tradeSummarySort.asc = false;
            }
            renderTradeSummary();
          });
        });
      }
      const sorted = sortTradeSummary(summary.accounts);
      sorted.forEach(acc => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${acc.name}</td>
          <td>₹${acc.live_balance?.toFixed(2) || 0}</td>
          <td class="${acc.net_pnl >= 0 ? 'green' : 'red'}">₹${acc.net_pnl}</td>
          <td>${acc.total_trades}</td>
          <td>${acc.wins}</td>
          <td>${acc.losses}</td>
          <td class="${acc.win_rate >= 50 ? 'green' : 'red'}">${acc.win_rate}%</td>
          <td>${acc.top_symbol}</td>
        `;
        tbody.appendChild(row);
      });
    });
}

// Toast helper
function showToast(message, success = true) {
  const toast = document.createElement('div');
  toast.className = `toast ${success ? 'bg-success' : 'bg-danger'} text-white`;
  toast.style.position = 'fixed';
  toast.style.bottom = '20px';
  toast.style.left = '50%';
  toast.style.transform = 'translateX(-50%)';
  toast.style.padding = '10px 20px';
  toast.style.borderRadius = '6px';
  toast.style.zIndex = 9999;
  toast.innerText = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Sound alert
function playSoundAlert() {
  const audio = new Audio('/static/notify.mp3');
  audio.play();
}

// Initial call
function loadAll() {
  fetch('/get-accounts-details')
    .then(res => res.json())
    .then(data => {
      loadAccounts();
      renderCopyTradingView(data);
    });
}

document.addEventListener("DOMContentLoaded", () => {
  const darkModeToggle = document.getElementById("dark-mode-toggle");
  if (darkModeToggle) darkModeToggle.addEventListener("change", toggleDarkMode);
  loadAll();
  renderTradeSummary();
});
setInterval(() => {
  loadAll();
  renderTradeSummary();
}, 60000);

function loadChartinkLog() {
  fetch('/chartink-log')
    .then(res => res.json())
    .then(data => {
      const tbody = document.getElementById("chartinkBody");
      if (!tbody) return;
      tbody.innerHTML = "";
      data.log.reverse().forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${new Date(row.timestamp).toLocaleString()}</td>
          <td>${row.symbol}</td>
          <td>${row.qty}</td>
          <td>${row.action}</td>
          <td><button onclick="openChart('${row.symbol}')">📈 View</button></td>
        `;
        tbody.appendChild(tr);
      });
    });
}

function showTab(id) {
  const sections = ['accountSection', 'copySection', 'summarySection', 'chartinkSection'];
  sections.forEach(sec => {
    const el = document.getElementById(sec);
    if (el) el.style.display = (sec === id) ? 'block' : 'none';
  });
  if (id === 'chartinkSection') loadChartinkLog();
}

function setZerodhaLoginLink() {
  const apiKey = "sa1t1c8gddb98915";
  const clientId = "BL1330";
  const redirectUri = "https://openalgo-dashboard.ontender.com/login-kite/" + clientId;
  const loginUrl = `https://kite.trade/connect/login?api_key=${apiKey}&v=3&redirect_uri=${encodeURIComponent(redirectUri)}`;
  const link = document.getElementById("zerodhaLoginBtn");
  if (link) link.href = loginUrl;
}
document.addEventListener("DOMContentLoaded", setZerodhaLoginLink);