(() => {
  const node = id => document.getElementById(id);
  const endpoint = window.OPENBAND_ANALYTICS_CONFIG?.apiEndpoint;
  const apiBase = endpoint ? new URL("/v1/creator-support/", endpoint) : null;

  async function request(path, options) {
    if (!apiBase) throw new Error("unavailable");
    const response = await fetch(new URL(path, apiBase), {
      ...options, cache: "no-store", signal: AbortSignal.timeout(15000)
    });
    if (!response.ok) {
      const error = new Error("request_failed");
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  const post = (path, payload) => request(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });

  function setupDonation(form) {
    const amountField = node("customAmountField");
    const custom = node("customAmount");
    const submit = node("continuePayment");
    const status = node("supportStatus");
    const error = node("supportError");
    let available = false;
    let attempt;
    let attemptAmount;
    let submitting = false;
    const cancelled = new URLSearchParams(location.search).get("cancelled") === "1";
    const defaultLabel = submit.textContent;

    const clearError = () => {
      error.hidden = true;
      custom.removeAttribute("aria-invalid");
    };
    const showError = message => {
      error.textContent = message;
      error.hidden = false;
    };
    const resetButton = () => {
      submitting = false;
      submit.textContent = defaultLabel;
      submit.disabled = !available;
    };

    const syncCustom = () => { amountField.hidden = form.elements.amount.value !== "custom"; };
    syncCustom();
    form.addEventListener("change", () => {
      syncCustom();
      clearError();
    });
    custom.addEventListener("input", clearError);
    window.addEventListener("pageshow", event => {
      if (!event.persisted) return;
      // Going back from Stripe starts a fresh attempt rather than reusing a completed session.
      attempt = undefined;
      resetButton();
    });

    request("config").then(config => {
      available = config.enabled === true;
      const messages = [];
      if (cancelled) messages.push("Checkout was cancelled. You can choose an amount to try again.");
      if (!available) messages.push("Online tips are currently unavailable.");
      else if (config.testMode) messages.push("Stripe test mode is active. No real payment will be collected.");
      status.textContent = messages.join(" ");
      resetButton();
    }).catch(() => {
      status.textContent = "Online tips are currently unavailable.";
    });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!available || submitting) return;
      clearError();
      const choice = form.elements.amount.value;
      const payload = {};
      if (choice === "custom") {
        const amount = custom.value.trim();
        const format = /^\d{1,6}(?:[.,]\d{1,2})?$/;
        if (!format.test(amount) || Number(amount.replace(",", ".")) < 2) {
          showError("Enter an amount from $2 to $999,999.99 CAD with up to two decimal places.");
          custom.setAttribute("aria-invalid", "true");
          custom.focus();
          return;
        }
        payload.customAmount = amount.replace(",", ".");
      } else {
        payload.presetCents = Number(choice);
      }
      const amountKey = JSON.stringify(payload);
      if (!attempt || attemptAmount !== amountKey) {
        attempt = crypto.randomUUID();
        attemptAmount = amountKey;
      }
      submitting = true;
      submit.disabled = true;
      submit.textContent = "Opening Stripe Checkout…";
      try {
        const {url} = await post("checkout", {...payload, attempt});
        if (new URL(url).origin !== "https://checkout.stripe.com") throw new Error("invalid_checkout");
        location.assign(url);
      } catch (caught) {
        if (caught.status === 400) showError("Choose a valid tip amount and try again.");
        else if (caught.status === 429) showError("Too many attempts. Please wait a minute and try again.");
        else showError("Stripe Checkout could not be opened. Please try again shortly.");
        resetButton();
      }
    });
  }

  async function setupConfirmation() {
    const status = node("confirmationStatus");
    const retry = node("confirmationRetry");
    const sessionId = new URLSearchParams(location.search).get("session_id");
    if (!sessionId || !/^cs_(test|live)_[a-zA-Z0-9]{1,200}$/.test(sessionId)) {
      status.textContent = "Open your Stripe return link to check your payment.";
      return;
    }
    async function check() {
      retry.hidden = true;
      status.textContent = "Checking for payment confirmation…";
      try {
        for (const delay of [0, 1000, 2000, 4000, 8000, 12000]) {
          if (delay) await new Promise(resolve => setTimeout(resolve, delay));
          const result = await post("confirmation", {sessionId});
          if (result.status === "paid") {
            node("confirmationPending").hidden = true;
            node("confirmationPaid").hidden = false;
            node("thankYouTitle").focus();
            return;
          }
          if (result.status === "failed" || result.status === "expired") {
            status.textContent = "Stripe did not confirm this payment. You can return to the support page to try again.";
            const link = document.createElement("a");
            link.href = "/support/";
            link.textContent = "Return to creator support";
            status.after(link);
            return;
          }
        }
        status.textContent = "Payment confirmation is still pending. Check again in a moment.";
      } catch (caught) {
        if (caught.status === 400 || caught.status === 404) {
          status.textContent = "We could not find a payment for this checkout.";
          return;
        }
        status.textContent = "Payment confirmation is temporarily unavailable. Try checking again shortly.";
      }
      retry.hidden = false;
    }
    retry.addEventListener("click", check);
    await check();
  }

  if (node("supportForm")) setupDonation(node("supportForm"));
  if (node("supportConfirmation")) void setupConfirmation();

  if (node("supportAdminLogin")) {
    const login = node("supportAdminLogin");
    const form = node("supportAdminForm");
    const dashboard = node("supportAdminReport");
    const error = node("supportAdminError");
    const money = new Intl.NumberFormat("en-CA", {style: "currency", currency: "CAD"});
    const date = new Intl.DateTimeFormat("en-CA", {dateStyle: "medium", timeStyle: "short", timeZone: "America/Regina"});
    const formatAmount = cents => money.format(cents / 100);
    const statusLabels = {paid: "Paid", pending: "Pending", failed: "Failed", expired: "Expired"};
    form.addEventListener("submit", async event => {
      event.preventDefault();
      form.querySelector("button").disabled = true;
      error.hidden = true;
      const input = node("supportAdminToken");
      const token = input.value;
      input.value = "";
      try {
        const data = await request("admin", {headers: {Authorization: `Bearer ${token}`}});
        node("supportAdminMode").textContent = data.mode === "test" ? "Stripe test mode" : "Stripe live mode";
        node("supportNet").textContent = formatAmount(data.summary.netCents);
        node("supportCount").textContent = data.summary.successfulCount.toLocaleString("en-CA");
        const table = node("supportTransactions");
        for (const item of data.transactions) {
          const row = table.insertRow();
          const refund = [];
          if (item.refundedCents > 0) {
            const kind = item.refundedCents === item.amountCents ? "Fully refunded" : "Partially refunded";
            refund.push(`${kind} (${formatAmount(item.refundedCents)})`);
          }
          if (item.refundPending) refund.push("Pending");
          if (item.refundFailed) refund.push("Failed or cancelled");
          const cells = [date.format(item.date * 1000), formatAmount(item.amountCents), item.reference,
            statusLabels[item.status] || item.status, refund.join(" · ") || "None"];
          for (const value of cells) row.insertCell().textContent = value;
        }
        node("supportEmpty").hidden = data.transactions.length > 0;
        table.closest("table").hidden = data.transactions.length === 0;
        login.hidden = true;
        dashboard.hidden = false;
        node("supportReportTitle").focus();
      } catch (caught) {
        error.textContent = caught.status === 401
          ? "The administrator token was not accepted."
          : "The Creator Support report is currently unavailable.";
        error.hidden = false;
      } finally {
        form.querySelector("button").disabled = false;
      }
    });
    node("supportSignOut").addEventListener("click", () => {
      dashboard.hidden = true;
      node("supportTransactions").replaceChildren();
      for (const id of ["supportNet", "supportCount", "supportAdminMode"]) node(id).textContent = "";
      login.hidden = false;
      node("supportAdminToken").focus();
    });
  }
})();
