const $ = (selector) => document.querySelector(selector);

let currentNota = null;
let currentAnalysis = null;
let peopleRows = [];
let classificationRows = [];
let accountRows = [];
let peopleMode = { busca: "", tipo: "", todos: false, inativos: false };
let classificationMode = { busca: "", tipo: "", todos: false, inativos: false };
let accountMode = { busca: "", todos: false };
const tableSort = {};

class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

async function apiRequest(url, options = {}) {
    const requestOptions = { ...options, credentials: "same-origin" };
    const headers = new Headers(options.headers || {});

    if (options.body && !(options.body instanceof FormData) && typeof options.body !== "string") {
        headers.set("Content-Type", "application/json");
        requestOptions.body = JSON.stringify(options.body);
    }
    requestOptions.headers = headers;

    const response = await fetch(url, requestOptions);
    if (response.status === 204) return null;

    let payload;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        payload = await response.json();
    } else {
        payload = { detail: await response.text() };
    }

    if (!response.ok) {
        if (response.status === 401 && url !== "/api/auth/login") {
            showLogin("Sua sessão expirou. Entre novamente.");
        }
        throw new ApiError(payload.detail || "Não foi possível concluir a operação.", response.status);
    }
    return payload;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatCurrency(value) {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value || 0));
}

function showLogin(message = "") {
    $("#appShell").classList.add("hidden");
    $("#loginScreen").classList.remove("hidden");
    $("#loginMessage").textContent = message;
    $("#passwordInput").value = "";
}

function showApp() {
    $("#loginScreen").classList.add("hidden");
    $("#appShell").classList.remove("hidden");
    $("#loginMessage").textContent = "";
}

async function loadVersion() {
    try {
        const data = await apiRequest("/api/versao");
        const commit = data.commitCurto || "NAO PUBLICADO";
        $("#versionText").textContent = commit;
        $("#versionText").title = data.commit || "Commit ainda não informado pelo provedor";
        $("#footerVersion").textContent = `Código: ${commit}`;
    } catch (error) {
        $("#versionText").textContent = "indisponível";
        $("#footerVersion").textContent = "Código: indisponível";
    }
}

async function initialize() {
    await loadVersion();
    try {
        const status = await apiRequest("/api/auth/status");
        if (status.autenticado) {
            showApp();
        } else {
            showLogin();
        }
    } catch (error) {
        showLogin(error.message);
    }
}

$("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type='submit']");
    button.disabled = true;
    $("#loginMessage").textContent = "Validando acesso...";
    try {
        await apiRequest("/api/auth/login", {
            method: "POST",
            body: {
                login: $("#loginInput").value.trim(),
                senha: $("#passwordInput").value,
            },
        });
        showApp();
        await loadVersion();
    } catch (error) {
        $("#loginMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#logoutButton").addEventListener("click", async () => {
    try {
        await apiRequest("/api/auth/logout", { method: "POST" });
    } finally {
        showLogin("Sessão encerrada.");
    }
});

// Navegação entre as telas.
document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", () => {
        document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        document.querySelectorAll(".view-section").forEach((view) => view.classList.add("hidden"));
        $(`#view-${button.dataset.view}`).classList.remove("hidden");
    });
});

// ============================================================
// EXTRAÇÃO DE NOTA FISCAL
// ============================================================

const pdfInput = $("#pdfInput");
$("#selectFileButton").addEventListener("click", () => pdfInput.click());

pdfInput.addEventListener("change", () => {
    const file = pdfInput.files[0];
    if (!file) return;

    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        window.alert("Selecione um arquivo PDF.");
        resetFile();
        return;
    }
    if (file.size > 20 * 1024 * 1024) {
        window.alert("O PDF deve possuir no máximo 20 MB.");
        resetFile();
        return;
    }

    $("#fileName").textContent = file.name;
    $("#selectedFileName").textContent = file.name;
    $("#selectedFileSize").textContent = formatFileSize(file.size);
    $("#selectedFile").classList.remove("hidden");
    $("#extractButton").disabled = false;
    $("#extractMessage").textContent = "";
    $("#resultSection").classList.add("hidden");
    $("#analysisSection").classList.add("hidden");
    $("#registrationMessage").textContent = "";
    currentNota = null;
    currentAnalysis = null;
});

$("#removeFileButton").addEventListener("click", resetFile);

function resetFile() {
    pdfInput.value = "";
    $("#fileName").textContent = "Nenhum arquivo selecionado";
    $("#selectedFileName").textContent = "";
    $("#selectedFileSize").textContent = "";
    $("#selectedFile").classList.add("hidden");
    $("#resultSection").classList.add("hidden");
    $("#analysisSection").classList.add("hidden");
    $("#extractButton").disabled = true;
    $("#extractMessage").textContent = "";
    $("#registrationMessage").textContent = "";
    currentNota = null;
    currentAnalysis = null;
}

$("#extractButton").addEventListener("click", async () => {
    const file = pdfInput.files[0];
    if (!file) {
        $("#extractMessage").textContent = "Selecione uma nota fiscal primeiro.";
        return;
    }

    const button = $("#extractButton");
    button.disabled = true;
    button.textContent = "Extraindo dados...";
    $("#extractMessage").textContent = "Enviando PDF ao Gemini. Isso pode levar alguns segundos.";
    $("#resultSection").classList.add("hidden");
    $("#analysisSection").classList.add("hidden");

    try {
        const formData = new FormData();
        formData.append("arquivo", file);
        currentNota = await apiRequest("/api/extrair-nota", { method: "POST", body: formData });
        $("#jsonResult").textContent = JSON.stringify(currentNota, null, 4);
        $("#resultSection").classList.remove("hidden");
        $("#extractMessage").textContent = "Extração concluída. Consultando os registros existentes...";

        currentAnalysis = await apiRequest("/api/analisar-nota", {
            method: "POST",
            body: currentNota,
        });
        renderAnalysis(currentAnalysis);
        $("#extractMessage").textContent = "Extração e consulta ao banco concluídas. Confira o resultado abaixo.";
        $("#resultSection").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        $("#extractMessage").textContent = error.message;
        $("#extractMessage").classList.add("error-text");
    } finally {
        button.disabled = !pdfInput.files[0];
        button.textContent = "Extrair dados com Gemini";
    }
});

function statusCard(title, item) {
    const exists = Boolean(item.existe);
    const statusClass = !exists ? "status-missing" : item.status === "INATIVO" ? "status-inactive" : "status-ok";
    return `
        <article class="status-card">
            <div class="status-card-head"><h3>${escapeHtml(title)}</h3><span class="status-pill ${statusClass}">${exists ? escapeHtml(item.status || "EXISTE") : "NÃO EXISTE"}</span></div>
            <p class="status-name">${escapeHtml(item.nome || item.descricao || "Não identificado")}</p>
            <p class="status-message">${escapeHtml(item.mensagem || "")}</p>
        </article>`;
}

function renderAnalysis(analysis) {
    const boxes = [statusCard("Fornecedor", analysis.fornecedor), statusCard("Faturado", analysis.faturado)];
    (analysis.despesas || []).forEach((item, index) => boxes.push(statusCard(`Despesa ${index + 1}`, item)));
    if (!(analysis.despesas || []).length) {
        boxes.push(`<article class="status-card status-warning"><h3>Classificação de despesa</h3><p>O Gemini não identificou uma classificação. Revise o JSON antes de registrar.</p></article>`);
    }
    $("#analysisResults").innerHTML = boxes.join("");
    $("#analysisSection").classList.remove("hidden");
    $("#registerButton").disabled = !(analysis.despesas || []).length;
}

$("#registerButton").addEventListener("click", async () => {
    if (!currentNota) return;
    const button = $("#registerButton");
    button.disabled = true;
    button.textContent = "Registrando...";
    $("#registrationMessage").textContent = "Criando cadastros ausentes e registrando movimento e parcela...";
    $("#registrationMessage").classList.remove("error-text", "success-text");
    try {
        const result = await apiRequest("/api/registrar-conta", { method: "POST", body: currentNota });
        $("#registrationMessage").textContent = `${result.mensagem} Movimento ID: ${result.movimentoId}. Parcelas criadas: ${result.parcelas.length}.`;
        $("#registrationMessage").classList.add("success-text");
        button.textContent = "Conta registrada";
        await loadAccounts({ todos: true });
    } catch (error) {
        $("#registrationMessage").textContent = error.message;
        $("#registrationMessage").classList.add("error-text");
        button.disabled = false;
        button.textContent = "Cadastrar o que falta e lançar conta a pagar";
    }
});

$("#copyButton").addEventListener("click", async () => {
    try {
        await navigator.clipboard.writeText($("#jsonResult").textContent);
        const button = $("#copyButton");
        const original = button.textContent;
        button.textContent = "JSON copiado";
        setTimeout(() => (button.textContent = original), 1800);
    } catch (error) {
        window.alert("Não foi possível copiar o JSON neste navegador.");
    }
});

function formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";
    const units = ["Bytes", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / Math.pow(1024, index)).toFixed(2)} ${units[index]}`;
}

// ============================================================
// TABELAS, PESQUISA E ORDENACAO POR COLUNA
// ============================================================

function renderTable(tableId, emptyId, countId, rows, columns, actionBuilder, emptyText, sortKey) {
    const table = $(`#${tableId}`);
    const empty = $(`#${emptyId}`);
    const count = $(`#${countId}`);
    if (!rows.length) {
        table.innerHTML = "";
        empty.textContent = emptyText;
        empty.classList.remove("hidden");
        count.textContent = "0 registros";
        return;
    }

    const state = tableSort[sortKey] || { field: columns[0].key, direction: "asc" };
    const sortedRows = [...rows].sort((a, b) => {
        const aValue = a[state.field] ?? "";
        const bValue = b[state.field] ?? "";
        const compared = typeof aValue === "number" && typeof bValue === "number"
            ? aValue - bValue
            : String(aValue).localeCompare(String(bValue), "pt-BR", { numeric: true, sensitivity: "base" });
        return state.direction === "asc" ? compared : -compared;
    });

    table.innerHTML = `
        <thead><tr>${columns.map((column) => `<th scope="col" data-sort-field="${escapeHtml(column.key)}" title="Clique para ordenar">${escapeHtml(column.label)} <span class="sort-indicator">${state.field === column.key ? (state.direction === "asc" ? "↑" : "↓") : "↕"}</span></th>`).join("")}<th scope="col">Ações</th></tr></thead>
        <tbody>${sortedRows.map((row) => `<tr>${columns.map((column) => `<td>${column.render ? column.render(row) : escapeHtml(row[column.key] ?? "—")}</td>`).join("")}<td class="actions-cell">${actionBuilder ? actionBuilder(row) : "—"}</td></tr>`).join("")}</tbody>`;
    empty.classList.add("hidden");
    count.textContent = `${rows.length} ${rows.length === 1 ? "registro" : "registros"}`;

    table.querySelectorAll("th[data-sort-field]").forEach((header) => {
        header.addEventListener("click", () => {
            const field = header.dataset.sortField;
            const previous = tableSort[sortKey] || { field: columns[0].key, direction: "asc" };
            tableSort[sortKey] = {
                field,
                direction: previous.field === field && previous.direction === "asc" ? "desc" : "asc",
            };
            renderTable(tableId, emptyId, countId, rows, columns, actionBuilder, emptyText, sortKey);
        });
    });
}

function personActions(row) {
    const action = row.status === "ATIVO"
        ? `<button class="table-action" data-kind="person" data-action="inativar" data-id="${row.id}">Inativar</button>`
        : `<button class="table-action reactivate" data-kind="person" data-action="reativar" data-id="${row.id}">Reativar</button>`;
    return `<button class="table-action" data-kind="person" data-action="editar" data-id="${row.id}">Editar</button>${action}`;
}

function classificationActions(row) {
    const action = row.status === "ATIVO"
        ? `<button class="table-action" data-kind="classificacao" data-action="inativar" data-id="${row.id}">Inativar</button>`
        : `<button class="table-action reactivate" data-kind="classificacao" data-action="reativar" data-id="${row.id}">Reativar</button>`;
    return `<button class="table-action" data-kind="classificacao" data-action="editar" data-id="${row.id}">Editar</button>${action}`;
}

function renderPeople() {
    renderTable(
        "peopleTable", "peopleEmpty", "peopleCount", peopleRows,
        [
            { key: "id", label: "ID" },
            { key: "tipo", label: "Tipo", render: (row) => escapeHtml(row.tipo === "FATURADO" ? "Faturado" : "Cliente/Fornecedor") },
            { key: "razao_social", label: "Nome / Razão social" },
            { key: "cnpj", label: "CNPJ" },
            { key: "cpf", label: "CPF" },
            { key: "status", label: "Status", render: (row) => `<span class="status-pill ${row.status === "ATIVO" ? "status-ok" : "status-inactive"}">${escapeHtml(row.status)}</span>` },
        ], personActions, "Nenhuma pessoa encontrada para esta consulta.", "pessoas"
    );
}

function renderClassifications() {
    renderTable(
        "classificationsTable", "classificationsEmpty", "classificationsCount", classificationRows,
        [
            { key: "id", label: "ID" },
            { key: "tipo", label: "Tipo", render: (row) => escapeHtml(row.tipo === "DESPESA" ? "Despesa" : "Receita") },
            { key: "descricao", label: "Descrição" },
            { key: "status", label: "Status", render: (row) => `<span class="status-pill ${row.status === "ATIVO" ? "status-ok" : "status-inactive"}">${escapeHtml(row.status)}</span>` },
        ], classificationActions, "Nenhuma classificação encontrada para esta consulta.", "classificacoes"
    );
}

function renderAccounts() {
    renderTable(
        "accountsTable", "accountsEmpty", "accountsCount", accountRows,
        [
            { key: "id", label: "ID" },
            { key: "numeroNotaFiscal", label: "Nota fiscal" },
            { key: "fornecedor", label: "Fornecedor" },
            { key: "faturado", label: "Faturado" },
            { key: "dataEmissao", label: "Emissão" },
            { key: "valorTotal", label: "Valor total", render: (row) => escapeHtml(formatCurrency(row.valorTotal)) },
            { key: "classificacoes", label: "Despesas", render: (row) => escapeHtml((row.classificacoes || []).map((item) => item.descricao).join(", ")) },
            { key: "parcelas", label: "Parcelas", render: (row) => escapeHtml((row.parcelas || []).map((item) => `${item.numero}: ${item.dataVencimento || "sem vencimento"}`).join("; ")) },
        ], () => "—", "Nenhuma conta encontrada para esta consulta.", "contas"
    );
}

async function loadPeople(mode = {}) {
    peopleMode = { busca: mode.busca || "", tipo: mode.tipo ?? $("#personTypeFilter").value, todos: Boolean(mode.todos), inativos: Boolean(mode.inativos) };
    const params = new URLSearchParams();
    if (peopleMode.busca) params.set("busca", peopleMode.busca);
    if (peopleMode.tipo) params.set("tipo", peopleMode.tipo);
    if (peopleMode.todos) params.set("todos", "true");
    if (peopleMode.inativos) params.set("inativos", "true");
    try {
        peopleRows = await apiRequest(`/api/pessoas?${params.toString()}`);
        renderPeople();
    } catch (error) {
        peopleRows = [];
        renderPeople();
        window.alert(error.message);
    }
}

async function loadClassifications(mode = {}) {
    classificationMode = { busca: mode.busca || "", tipo: mode.tipo ?? $("#classificationTypeFilter").value, todos: Boolean(mode.todos), inativos: Boolean(mode.inativos) };
    const params = new URLSearchParams();
    if (classificationMode.busca) params.set("busca", classificationMode.busca);
    if (classificationMode.tipo) params.set("tipo", classificationMode.tipo);
    if (classificationMode.todos) params.set("todos", "true");
    if (classificationMode.inativos) params.set("inativos", "true");
    try {
        classificationRows = await apiRequest(`/api/classificacoes?${params.toString()}`);
        renderClassifications();
    } catch (error) {
        classificationRows = [];
        renderClassifications();
        window.alert(error.message);
    }
}

async function loadAccounts(mode = {}) {
    accountMode = { busca: mode.busca || "", todos: Boolean(mode.todos) };
    const params = new URLSearchParams();
    if (accountMode.busca) params.set("busca", accountMode.busca);
    if (accountMode.todos) params.set("todos", "true");
    try {
        accountRows = await apiRequest(`/api/contas?${params.toString()}`);
        renderAccounts();
    } catch (error) {
        accountRows = [];
        renderAccounts();
        if (error.status !== 401) window.alert(error.message);
    }
}

$("#searchPeopleButton").addEventListener("click", () => loadPeople({ busca: $("#personSearch").value.trim(), tipo: $("#personTypeFilter").value }));
$("#allPeopleButton").addEventListener("click", () => loadPeople({ todos: true, tipo: $("#personTypeFilter").value }));
$("#inactivePeopleButton").addEventListener("click", () => loadPeople({ inativos: true, tipo: $("#personTypeFilter").value }));
$("#personSearch").addEventListener("keydown", (event) => { if (event.key === "Enter") $("#searchPeopleButton").click(); });

$("#searchClassificationsButton").addEventListener("click", () => loadClassifications({ busca: $("#classificationSearch").value.trim(), tipo: $("#classificationTypeFilter").value }));
$("#allClassificationsButton").addEventListener("click", () => loadClassifications({ todos: true, tipo: $("#classificationTypeFilter").value }));
$("#inactiveClassificationsButton").addEventListener("click", () => loadClassifications({ inativos: true, tipo: $("#classificationTypeFilter").value }));
$("#classificationSearch").addEventListener("keydown", (event) => { if (event.key === "Enter") $("#searchClassificationsButton").click(); });

$("#searchAccountsButton").addEventListener("click", () => loadAccounts({ busca: $("#accountSearch").value.trim() }));
$("#allAccountsButton").addEventListener("click", () => loadAccounts({ todos: true }));
$("#accountSearch").addEventListener("keydown", (event) => { if (event.key === "Enter") $("#searchAccountsButton").click(); });

// ============================================================
// DIALOGS DE CADASTRO / EDICAO
// ============================================================

function openDialog(dialogId) {
    const dialog = $(`#${dialogId}`);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");
}

function closeDialog(dialogId) {
    const dialog = $(`#${dialogId}`);
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
}

document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => closeDialog(button.dataset.closeDialog));
});

$("#newPersonButton").addEventListener("click", () => {
    $("#personForm").reset();
    $("#personId").value = "";
    $("#personDialogTitle").textContent = "Nova pessoa";
    $("#personFormMessage").textContent = "";
    openDialog("personDialog");
});

$("#personFormType").addEventListener("change", () => {
    const isFaturado = $("#personFormType").value === "FATURADO";
    $("#personFantasy").disabled = isFaturado;
    if (isFaturado) $("#personFantasy").value = "";
});

$("#personForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("#personId").value;
    const payload = {
        tipo: $("#personFormType").value,
        razao_social: $("#personName").value.trim(),
        nome_fantasia: $("#personFantasy").value.trim(),
        cnpj: $("#personCnpj").value.trim(),
        cpf: $("#personCpf").value.trim(),
    };
    try {
        await apiRequest(id ? `/api/pessoas/${id}` : "/api/pessoas", { method: id ? "PUT" : "POST", body: payload });
        closeDialog("personDialog");
        await loadPeople({ todos: true, tipo: $("#personTypeFilter").value });
    } catch (error) {
        $("#personFormMessage").textContent = error.message;
    }
});

$("#newClassificationButton").addEventListener("click", () => {
    $("#classificationForm").reset();
    $("#classificationId").value = "";
    $("#classificationDialogTitle").textContent = "Nova classificação";
    $("#classificationFormMessage").textContent = "";
    openDialog("classificationDialog");
});

$("#classificationForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = $("#classificationId").value;
    const payload = { tipo: $("#classificationFormType").value, descricao: $("#classificationDescription").value.trim() };
    try {
        await apiRequest(id ? `/api/classificacoes/${id}` : "/api/classificacoes", { method: id ? "PUT" : "POST", body: payload });
        closeDialog("classificationDialog");
        await loadClassifications({ todos: true, tipo: $("#classificationTypeFilter").value });
    } catch (error) {
        $("#classificationFormMessage").textContent = error.message;
    }
});

document.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-kind][data-action][data-id]");
    if (!button) return;

    const { kind, action, id } = button.dataset;
    const numericId = Number(id);
    try {
        if (kind === "person" && action === "editar") {
            const row = peopleRows.find((item) => item.id === numericId);
            if (!row) return;
            $("#personId").value = row.id;
            $("#personFormType").value = row.tipo;
            $("#personName").value = row.razao_social || "";
            $("#personFantasy").value = row.nome_fantasia || "";
            $("#personCnpj").value = row.cnpj || "";
            $("#personCpf").value = row.cpf || "";
            $("#personFantasy").disabled = row.tipo === "FATURADO";
            $("#personDialogTitle").textContent = `Editar pessoa #${row.id}`;
            $("#personFormMessage").textContent = "";
            openDialog("personDialog");
            return;
        }
        if (kind === "classificacao" && action === "editar") {
            const row = classificationRows.find((item) => item.id === numericId);
            if (!row) return;
            $("#classificationId").value = row.id;
            $("#classificationFormType").value = row.tipo;
            $("#classificationDescription").value = row.descricao;
            $("#classificationDialogTitle").textContent = `Editar classificação #${row.id}`;
            $("#classificationFormMessage").textContent = "";
            openDialog("classificationDialog");
            return;
        }

        const isPerson = kind === "person";
        const base = isPerson ? "/api/pessoas" : "/api/classificacoes";
        const label = isPerson ? "pessoa" : "classificação";
        if (action === "inativar") {
            if (!window.confirm(`Deseja inativar esta ${label}? O registro não será apagado definitivamente.`)) return;
            await apiRequest(`${base}/${numericId}`, { method: "DELETE" });
        } else if (action === "reativar") {
            await apiRequest(`${base}/${numericId}/reativar`, { method: "POST" });
        }
        if (isPerson) await loadPeople(peopleMode);
        else await loadClassifications(classificationMode);
    } catch (error) {
        window.alert(error.message);
    }
});

// Mostra uma mensagem simples caso um dialog seja fechado com Esc.
document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });
});

initialize();
