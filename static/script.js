async function fetchData() {
    const wallets = await fetch('/wallets').then(res => res.json());
    const transactions = await fetch('/transactions').then(res => res.json());
    const activity = await fetch('/activity').then(res => res.json());
    const validators = await fetch('/validators').then(res => res.json());

    // Wallets
    document.getElementById("wallets").innerHTML =
        wallets.map(w =>
            `<li>${w.address} : ${w.balance} coins</li>`
        ).join("");

    // Transactions (with timestamp + +/-)
    document.getElementById("transactions").innerHTML =
        transactions.map(t => `
            <li>
                 ${new Date(t.timestamp * 1000).toLocaleTimeString()} |
                ${t.from} → ${t.to} |
                ${t.from === "system" ? "+" : "-"}${t.amount}
                <br>
                 ${t.validator}
            </li>
        `).join("");

    // Stats
    const totalSupply = wallets.reduce((sum, w) => sum + w.balance, 0);

    document.getElementById("totalSupply").innerText = totalSupply;
    document.getElementById("totalWallets").innerText = wallets.length;
    document.getElementById("totalTransactions").innerText = transactions.length;
    document.getElementById("activeNodes").innerText = wallets.length;

    // Validators
    document.getElementById("validators").innerHTML =
        validators.map(v => `<li> ${v} Active</li>`).join("");

    // Activity
    document.getElementById("activity").innerHTML =
        activity.map(a => `<li>${a}</li>`).join("");
}

// Auto refresh
setInterval(fetchData, 2000);
fetchData();

// Clock
function updateClock() {
    const now = new Date();
    document.getElementById("clock").innerHTML =
        now.toLocaleTimeString();
}

setInterval(updateClock, 1000);
updateClock();
