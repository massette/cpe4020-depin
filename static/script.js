async function fetchData() {
    // reduce wallet transaction histories to their balance
    const wallets = (await fetch('/wallets').then(res => res.json()))
    const balances = Object.entries(wallets).map(
        ([address, blocks]) => [address, blocks.reduce(
            (sum, block) => (block["to"] == address)
            ? sum + block["amount"] : sum - block["amount"], 0)]);
    console.log(balances);

    // limit transaction history to last 20 transactions
    const transactions = (await fetch('/transactions').then(res => res.json()))
        .splice(-20);

    // request active validators
    const validators = await fetch('/validators').then(res => res.json());

    // Wallets
    document.getElementById("wallets").innerHTML =
        balances.map(([address, balance]) =>
            `<li>${address} : ${balance} coins</li>`
        ).join("");

    // Transactions (with timestamp + +/-)
    document.getElementById("transactions").innerHTML =
        transactions.map(t => `
            <li>
                ${t.validator} |
                ${new Date(t.timestamp * 1000).toLocaleTimeString()} |
                ${t.from.length < 16 ? t.from : t.from.substring(0, 16) + "..."} → ${t.to.substring(0, 16)}... |
                ${t.from === "MINT" ? "+" : "-"}${t.amount}
            </li>
        `).join("");

    // Stats
    const totalSupply = balances.reduce((sum, [address, balance]) => sum + balance, 0);

    document.getElementById("totalSupply").innerText = totalSupply;
    document.getElementById("totalWallets").innerText = Object.keys(wallets).length;
    document.getElementById("totalTransactions").innerText = transactions.length;
    document.getElementById("activeNodes").innerText = Object.keys(wallets).length + validators.length;

    // Validators
    document.getElementById("validators").innerHTML =
        validators.map(v => `<li> ${v} Active</li>`).join("");
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
