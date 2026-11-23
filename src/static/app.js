// ================= GLOBAL STATE =================
const state = {
    authenticated: false,
    currentStep: 1,
    user: { user_id: 1, name: "Vitor Cabral", role: "Operador" },
    customers: [],
    vessels: [],
    history: [],
    samples: [],
    processingId: null,
    fileInfo: null,
    extraction: null,
    imoMatch: null,
    nameSuggestions: [],
    selectedVesselId: "",
    selectedCustomerId: "",
    drafts: {
        destination_email: "",
        en: { subject: "", body: "" },
        pt: { subject: "", body: "" }
    },
    currentLang: "en",
    extendedVisible: false,
    approvalRecord: null
};

// ================= INITIALIZATION =================
document.addEventListener("DOMContentLoaded", async () => {
    setupDragAndDrop();
    await loadBootstrapData();
    // Pre-load the official prototype PDF so Step 1-6 are populated as soon as the user logs in
    await loadSampleFile("BOLETIM_ATLANTIC_STAR_1911.pdf", true);
});

async function loadBootstrapData() {
    try {
        const res = await fetch("/api/bootstrap");
        const data = await res.json();
        state.authenticated = Boolean(data.authenticated);
        state.user = data.user;
        state.users = data.users || [];
        state.customers = data.customers;
        state.vessels = data.vessels;
        state.history = data.history;
        state.samples = data.samples;

        updateUserSidebarUI();
        updateLoginOverlayVisibility();

        renderSamplesBar();
        populateSelectDropdowns();
        renderHistoryAndDbTables();
    } catch (err) {
        showToast("Erro ao inicializar dados do servidor.", "error");
    }
}

function getInitials(fullName) {
    if (!fullName) return "SG";
    const parts = fullName.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function updateUserSidebarUI() {
    const nameEl = document.getElementById("sidebarUserName");
    const roleEl = document.getElementById("sidebarUserRole");
    const avatarEl = document.getElementById("sidebarUserAvatar");
    if (nameEl) nameEl.textContent = state.user.name;
    if (roleEl) roleEl.textContent = state.user.role;
    if (avatarEl) avatarEl.textContent = getInitials(state.user.name);
}

function updateLoginOverlayVisibility() {
    const overlay = document.getElementById("loginOverlay");
    if (!overlay) return;
    if (state.authenticated) {
        overlay.classList.add("hidden");
    } else {
        overlay.classList.remove("hidden");
    }
}

function fillDemoCredentials(username) {
    document.getElementById("loginUsername").value = username;
    const pwdInput = document.getElementById("loginPassword");
    pwdInput.value = "";
    pwdInput.focus();
    document.getElementById("loginErrorBox").style.display = "none";
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value.trim();
    const errBox = document.getElementById("loginErrorBox");
    errBox.style.display = "none";

    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();

        if (!res.ok || !data.ok) {
            errBox.textContent = data.message || "Credenciais inválidas.";
            errBox.style.display = "block";
            return;
        }

        state.authenticated = true;
        state.user = data.user;
        updateUserSidebarUI();
        updateLoginOverlayVisibility();
        updateHeaderForStep(state.currentStep);
        renderStep6Approval();
        showToast(data.message, "success");
    } catch (err) {
        errBox.textContent = "Erro de conexão com o servidor SIGECAR.";
        errBox.style.display = "block";
    }
}

async function handleLogout() {
    try {
        await fetch("/api/logout", { method: "POST" });
        state.authenticated = false;
        const pwdInput = document.getElementById("loginPassword");
        if (pwdInput) pwdInput.value = "";
        updateLoginOverlayVisibility();
        showToast("Sessão encerrada com segurança.", "success");
    } catch (err) {
        showToast("Erro ao encerrar sessão.", "error");
    }
}

function renderSamplesBar() {
    const grid = document.getElementById("samplesGrid");
    if (!grid) return;
    grid.innerHTML = state.samples.map(s => {
        let badgeBg = "var(--sucesso-bg)";
        let badgeColor = "var(--sucesso)";
        if (s.type === "warning") {
            badgeBg = "var(--alerta-bg)";
            badgeColor = "var(--alerta)";
        } else if (s.type === "error") {
            badgeBg = "var(--erro-bg)";
            badgeColor = "var(--erro)";
        }
        return `
            <button type="button" class="sample-pill" onclick="loadSampleFile('${s.filename}')">
                <div class="sample-pill-top">
                    <span class="sample-pill-title">${escapeHtml(s.title)}</span>
                    <span class="sample-pill-badge" style="background:${badgeBg}; color:${badgeColor};">${escapeHtml(s.badge)}</span>
                </div>
                <div class="sample-pill-desc">${escapeHtml(s.description)}</div>
            </button>
        `;
    }).join("");
}

function toggleOperatorEmailModal() {
    const box = document.getElementById("operatorEmailBox");
    box.style.display = box.style.display === "none" ? "block" : "none";
}

// ================= DRAG & DROP / FILE UPLOAD =================
function setupDragAndDrop() {
    const dz = document.getElementById("dropzoneBox");
    if (!dz) return;

    ["dragenter", "dragover"].forEach(evtName => {
        dz.addEventListener(evtName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dz.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(evtName => {
        dz.addEventListener(evtName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dz.classList.remove("dragover");
        });
    });

    dz.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            uploadFileObject(files[0]);
        }
    });
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (files && files.length > 0) {
        uploadFileObject(files[0]);
        event.target.value = "";
    }
}

async function uploadFileObject(file) {
    // Client-side pre-check for > 5MB (CT03 / RNF01)
    if (file.size > 5 * 1024 * 1024) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        showUploadError(`Arquivo rejeitado (CT03): "${file.name}" possui ${sizeMb} MB e ultrapassa o limite máximo de 5 MB.`);
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    await sendUploadRequest(formData, false);
}

async function loadSampleFile(sampleName, silent = false) {
    const formData = new FormData();
    formData.append("sample_name", sampleName);
    await sendUploadRequest(formData, silent);
}

async function sendUploadRequest(formData, silent = false) {
    const errBox = document.getElementById("uploadErrorBox");
    errBox.style.display = "none";

    try {
        const res = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        if (!res.ok || !data.ok) {
            showUploadError(data.message || "Falha ao importar o documento.");
            return;
        }

        state.processingId = data.processing_id;
        state.fileInfo = data.file_info;
        state.extraction = data.extraction;
        state.imoMatch = data.imo_match;
        state.nameConflict = data.name_conflict || null;
        state.nameSuggestions = data.name_suggestions || [];
        state.drafts = data.drafts;
        state.approvalRecord = null;

        // Auto-expand extended fields if the bulletin has them
        state.extendedVisible = Boolean(data.extraction.has_extended_fields);

        // Set selected vessel and customer if exact IMO match was found
        if (state.imoMatch) {
            state.selectedVesselId = String(state.imoMatch.vessel_id);
            state.selectedCustomerId = String(state.imoMatch.customer_id);
        } else {
            state.selectedVesselId = "";
            state.selectedCustomerId = "";
        }

        renderStep1Upload();
        renderStep2Extraction();
        renderStep3Revision();
        renderStep4ManualRegistration();
        renderStep5EmailEditor();
        renderStep6Approval();

        if (!silent) {
            showToast(`Arquivo "${state.fileInfo.filename}" importado e validado com sucesso!`, "success");
            goToStep(1);
        }
    } catch (err) {
        showUploadError("Erro de comunicação ao enviar o arquivo para o servidor.");
    }
}

function showUploadError(msg) {
    const errBox = document.getElementById("uploadErrorBox");
    errBox.innerHTML = `<strong>✖ Falha na Importação / Validação:</strong> ${escapeHtml(msg)}`;
    errBox.style.display = "block";
    showToast(msg, "error");
}

// ================= RENDER STEP 1: UPLOAD =================
function renderStep1Upload() {
    if (!state.fileInfo) return;
    document.getElementById("receivedFileName").textContent = state.fileInfo.filename;
    document.getElementById("receivedFileDetails").textContent =
        `${state.fileInfo.size_formatted} • ${state.fileInfo.page_count} página${state.fileInfo.page_count > 1 ? "s" : ""} • Recebido às ${state.fileInfo.received_time_short}`;

    document.getElementById("previewPageCounter").textContent =
        `Pág. 1 / ${state.fileInfo.page_count}`;

    const portVal = (state.extraction?.fields?.port || "PARANAGUÁ").toUpperCase();
    document.getElementById("previewPortHeader").textContent =
        portVal !== "[NÃO INFORMADO]" ? portVal : "PARANAGUÁ";

    // Filter out header/footer lines from raw_text for the clean document preview sheet
    const lines = state.fileInfo.raw_text.split("\n").filter(l => {
        const up = l.trim().toUpperCase();
        return up &&
            !up.includes("BOLETIM OPERACIONAL PORTUÁRIO") &&
            up !== "PARANAGUÁ" &&
            !up.includes("DOCUMENTO PADRONIZADO PRONTO PARA LEITURA");
    });
    document.getElementById("previewRawText").textContent = lines.join("\n");
}

// ================= RENDER STEP 2: EXTRACTION =================
function renderStep2Extraction() {
    if (!state.extraction) return;
    const sum = state.extraction.summary;
    const meta = state.extraction.field_meta;

    document.getElementById("summaryFoundCount").innerHTML =
        `<i>✔</i> ${sum.found} campo${sum.found !== 1 ? "s" : ""} encontrado${sum.found !== 1 ? "s" : ""}`;
    document.getElementById("summaryPendingCount").innerHTML =
        `<i>⚠</i> ${sum.pending} campo${sum.pending !== 1 ? "s" : ""} pendente${sum.pending !== 1 ? "s" : ""}`;
    document.getElementById("summaryReadRate").textContent =
        `Taxa de leitura: ${sum.read_rate}%`;

    // Top 4 cards (Prototype Layout: Embarcação, Número IMO, Porto, Berço)
    const topKeys = ["vessel_name", "imo", "port", "berth"];
    document.getElementById("extractedCardsTop").innerHTML = topKeys
        .map(k => buildFieldCardHtml(meta[k]))
        .join("");

    // Bottom 3 cards (Prototype Layout: Status Operacional, Início da Operação, Término Previsto)
    const bottomKeys = ["status", "eta", "etc"];
    document.getElementById("extractedCardsBottom").innerHTML = bottomKeys
        .map(k => buildFieldCardHtml(meta[k]))
        .join("");

    // Extended 5 cards (Viagem, ETB, ETD, Carga, Observações) when present in the PDF
    const extKeys = ["voyage", "etb", "etd", "cargo", "notes"];
    const extContainer = document.getElementById("extractedCardsExtended");
    if (state.extraction.has_extended_fields) {
        extContainer.style.display = "grid";
        extContainer.style.gridTemplateColumns = "repeat(auto-fit, minmax(210px, 1fr))";
        extContainer.innerHTML = extKeys
            .filter(k => meta[k] && meta[k].include_in_cards)
            .map(k => buildFieldCardHtml(meta[k]))
            .join("");
    } else {
        extContainer.style.display = "none";
        extContainer.innerHTML = "";
    }

    // Bottom Info Message
    const infoMsg = document.getElementById("extractionInfoMessage");
    if (state.extraction.warnings && state.extraction.warnings.length > 0) {
        infoMsg.textContent = state.extraction.warnings.join(" • ");
    } else if (sum.pending > 0) {
        infoMsg.textContent = "A ausência de campos opcionais ou do término previsto não interrompe o fluxo. Complete na tela de Revisão.";
    } else {
        infoMsg.textContent = "Todos os campos do boletim operacional foram extraídos e validados com sucesso.";
    }
}

function buildFieldCardHtml(m) {
    if (!m) return "";
    const isPending = m.state !== "valid";
    const cardClass = isPending ? "field-card pending" : "field-card";
    const iconHtml = isPending
        ? `<span style="color: var(--alerta); font-size: 15px;">⚠</span>`
        : `<span style="color: var(--sucesso); font-size: 15px;">✔</span>`;

    const isMono = ["imo", "berth", "eta", "etb", "etc", "etd", "voyage"].includes(m.key) && !m.is_missing;
    const isStatusHighlight = m.key === "status" && !m.is_missing;
    let valClasses = "field-card-value";
    if (isMono) valClasses += " mono";
    if (isStatusHighlight) valClasses += " status-highlight";

    const displayVal = m.is_missing ? "Não identificado" : m.value;

    return `
        <div class="${cardClass}">
            <div class="field-card-header">
                <span>${escapeHtml(m.label)}</span>
                ${iconHtml}
            </div>
            <div class="${valClasses}">${escapeHtml(displayVal)}</div>
            <div class="field-card-footer">${escapeHtml(m.status_badge)}</div>
        </div>
    `;
}

// ================= RENDER STEP 3: REVISION & LINKING =================
function populateSelectDropdowns() {
    const selVessel = document.getElementById("selVessel");
    const selCustomer = document.getElementById("selCustomer");
    const regVesselCustomer = document.getElementById("regVesselCustomer");

    if (selVessel) {
        selVessel.innerHTML = `<option value="">-- Não vinculada / Vinculação manual --</option>` +
            state.vessels.map(v =>
                `<option value="${v.vessel_id}">${escapeHtml(v.vessel_name)} (${escapeHtml(v.imo)})</option>`
            ).join("");
    }

    const custOptions = state.customers.map(c =>
        `<option value="${c.customer_id}">${escapeHtml(c.company_name)}</option>`
    ).join("");

    if (selCustomer) {
        selCustomer.innerHTML = `<option value="">-- Selecione o cliente destinatário --</option>` + custOptions;
    }

    if (regVesselCustomer) {
        regVesselCustomer.innerHTML = custOptions;
    }
}

function renderStep3Revision() {
    if (!state.extraction) return;
    const meta = state.extraction.field_meta;

    const allKeys = ["vessel_name", "imo", "port", "berth", "status", "eta", "etc", "voyage", "etb", "etd", "cargo", "notes"];
    allKeys.forEach(k => {
        const inp = document.getElementById(`inp_${k}`);
        const lbl = document.getElementById(`lbl_${k}`);
        if (!inp || !meta[k]) return;

        const m = meta[k];
        if (m.is_missing) {
            inp.value = "Não identificado";
            inp.classList.add("pending-input");
            if (lbl) {
                lbl.classList.add("pending-label");
                if (k === "etc") lbl.textContent = "Término previsto (Ausente)";
            }
        } else {
            inp.value = m.raw_value || m.value;
            inp.classList.remove("pending-input");
            if (lbl) {
                lbl.classList.remove("pending-label");
                if (k === "etc") lbl.textContent = "Término previsto";
            }
        }
    });

    // Extended fields visibility
    const extDiv = document.getElementById("extendedRevisionFields");
    const btnText = document.getElementById("btnToggleExtendedText");
    if (state.extendedVisible) {
        extDiv.style.display = "block";
        btnText.textContent = "− Ocultar campos complementares";
    } else {
        extDiv.style.display = "none";
        btnText.textContent = "+ Mostrar campos completos (Viagem, ETB, ETD, Carga, Obs.)";
    }

    updateRevisionAlerts();

    // Populate vessel and customer selection
    populateSelectDropdowns();
    document.getElementById("selVessel").value = state.selectedVesselId || "";
    document.getElementById("selCustomer").value = state.selectedCustomerId || "";
    document.getElementById("chkSavePermanent").checked = false;

    updateDbMatchUI();
}

function toggleExtendedFields() {
    state.extendedVisible = !state.extendedVisible;
    const extDiv = document.getElementById("extendedRevisionFields");
    const btnText = document.getElementById("btnToggleExtendedText");
    if (state.extendedVisible) {
        extDiv.style.display = "block";
        btnText.textContent = "− Ocultar campos complementares";
    } else {
        extDiv.style.display = "none";
        btnText.textContent = "+ Mostrar campos completos (Viagem, ETB, ETD, Carga, Obs.)";
    }
}

function onFieldManualEdit(key) {
    const inp = document.getElementById(`inp_${key}`);
    const lbl = document.getElementById(`lbl_${key}`);
    if (!inp) return;

    const val = inp.value.trim();
    const isMissing = !val || val === "Não identificado" || val === "[Não informado]" || val === "-";
    if (isMissing) {
        inp.classList.add("pending-input");
        if (lbl) lbl.classList.add("pending-label");
    } else {
        inp.classList.remove("pending-input");
        if (lbl) {
            lbl.classList.remove("pending-label");
            if (key === "etc") lbl.textContent = "Término previsto";
        }
    }

    // If IMO was edited to 7 digits, check if it matches an existing vessel in DB
    if (key === "imo" && val.length === 7 && /^\d{7}$/.test(val)) {
        const matched = state.vessels.find(v => v.imo === val);
        if (matched) {
            state.imoMatch = matched;
            state.selectedVesselId = String(matched.vessel_id);
            state.selectedCustomerId = String(matched.customer_id);
            document.getElementById("selVessel").value = state.selectedVesselId;
            document.getElementById("selCustomer").value = state.selectedCustomerId;
            updateDbMatchUI();
            showToast(`Embarcação "${matched.vessel_name}" localizada pelo IMO ${val}!`, "success");
        }
    }

    updateRevisionAlerts();
}

function updateRevisionAlerts() {
    const coreKeys = ["vessel_name", "imo", "port", "berth", "status", "eta", "etc"];
    const missingLabels = [];
    coreKeys.forEach(k => {
        const inp = document.getElementById(`inp_${k}`);
        if (!inp) return;
        const v = inp.value.trim();
        if (!v || v === "Não identificado" || v === "[Não informado]" || v === "-") {
            const labelMap = {
                vessel_name: "Nome da embarcação",
                imo: "IMO",
                port: "Porto",
                berth: "Berço",
                status: "Status",
                eta: "Início da operação",
                etc: "Término previsto"
            };
            missingLabels.push(labelMap[k]);
        }
    });

    const alertBox = document.getElementById("revisionAlertBox");
    const extraWarnings = (state.extraction && state.extraction.warnings) ? state.extraction.warnings : [];

    if (missingLabels.length > 0 || extraWarnings.length > 0) {
        alertBox.className = "alert-box alert-warning";
        const parts = [];
        if (missingLabels.length > 0) {
            parts.push(`Campo(s) "${missingLabels.join('", "')}" não encontrado(s) no PDF. Preencha manualmente ou mantenha pendente ([Não informado]).`);
        }
        extraWarnings.forEach(w => parts.push(escapeHtml(w)));
        alertBox.innerHTML = `<strong>⚠ Alerta de Revisão:</strong><br>` + parts.join("<br>");
    } else {
        alertBox.className = "alert-box alert-success";
        alertBox.innerHTML = `<strong>✔ Conferência concluída:</strong> Todos os campos principais estão preenchidos e validados.`;
    }

    if (state.currentStep === 3) {
        updateHeaderForStep(3, missingLabels.length + extraWarnings.length);
    }
}

function resolveNameConflictWithReference(dbVesselName) {
    const inp = document.getElementById("inp_vessel_name");
    if (inp) {
        inp.value = dbVesselName;
        onFieldManualEdit("vessel_name");
    }
    state.nameConflict = null;
    if (state.extraction && state.extraction.warnings) {
        state.extraction.warnings = state.extraction.warnings.filter(w => !w.includes("o PDF informa o navio"));
    }
    updateRevisionAlerts();
    updateDbMatchUI();
    showToast(`Nome da embarcação corrigido para "${dbVesselName}" conforme o cadastro de referência!`, "success");
}

function updateDbMatchUI() {
    const badge = document.getElementById("dbMatchBadge");
    const sugBox = document.getElementById("nameSuggestionBox");
    const emailPill = document.getElementById("customerEmailPill");
    const emailText = document.getElementById("customerEmailText");

    const selectedCustomer = state.customers.find(c => String(c.customer_id) === String(state.selectedCustomerId));

    if (selectedCustomer) {
        emailPill.style.display = "flex";
        emailPill.style.backgroundColor = "var(--sucesso-bg)";
        emailPill.style.color = "var(--sucesso)";
        emailText.textContent = `E-mail: ${selectedCustomer.destination_email}`;
    } else {
        emailPill.style.display = "flex";
        emailPill.style.backgroundColor = "var(--alerta-bg)";
        emailPill.style.color = "var(--alerta)";
        emailText.textContent = "Aguardando seleção do cliente destinatário";
    }

    if (state.nameConflict) {
        badge.className = "badge badge-warning";
        badge.textContent = "⚠ Conflito Nome vs. IMO";
        const nc = state.nameConflict;
        sugBox.style.display = "block";
        sugBox.innerHTML = `
            <div style="margin-bottom: 8px;">
                <strong>⚠ Inconsistência Detectada (IMO ${escapeHtml(nc.imo)}):</strong><br>
                O PDF informa <strong>"${escapeHtml(nc.pdf_vessel_name)}"</strong>, mas no cadastro de referência o IMO <strong>${escapeHtml(nc.imo)}</strong> pertence a <strong>"${escapeHtml(nc.db_vessel_name)}"</strong> (${escapeHtml(nc.company_name)}).
            </div>
            <button type="button" class="btn btn-primary btn-sm" onclick="resolveNameConflictWithReference('${escapeHtml(nc.db_vessel_name)}')">
                ✔ Corrigir nome para ${escapeHtml(nc.db_vessel_name)} (Cadastro Oficial)
            </button>
        `;
    } else if (state.selectedVesselId) {
        badge.className = "badge badge-success";
        badge.textContent = "✔ Embarcação Vinculada";
        sugBox.style.display = "none";
    } else if (state.nameSuggestions && state.nameSuggestions.length > 0) {
        badge.className = "badge badge-warning";
        badge.textContent = "⚠ Confirmação Necessária";
        const s = state.nameSuggestions[0];
        sugBox.style.display = "block";
        sugBox.innerHTML = `
            <div style="margin-bottom: 8px;">
                <strong>🔎 Busca Auxiliar por Nome (RN02 / RF04):</strong><br>
                O IMO não foi localizado, mas encontramos a embarcação <strong>${escapeHtml(s.vessel_name)} (IMO ${escapeHtml(s.imo)})</strong> vinculada ao cliente <strong>${escapeHtml(s.company_name)}</strong>.
            </div>
            <button type="button" class="btn btn-primary btn-sm" onclick="confirmNameSuggestion(${s.vessel_id})">
                ✔ Confirmar vínculo com ${escapeHtml(s.vessel_name)} (IMO ${escapeHtml(s.imo)})
            </button>
        `;
    } else {
        badge.className = "badge badge-error";
        badge.textContent = "✖ IMO Não Encontrado";
        sugBox.style.display = "block";
        sugBox.innerHTML = `
            <strong>Cadastro não encontrado (RN03 / CT08):</strong> Nenhuma embarcação correspondente no banco. Selecione um cliente manualmente abaixo ou clique em <strong>"Cadastrar embarcação"</strong>.
        `;
    }
}

function confirmNameSuggestion(vesselId) {
    const v = state.vessels.find(x => x.vessel_id === vesselId);
    if (!v) return;
    state.selectedVesselId = String(v.vessel_id);
    state.selectedCustomerId = String(v.customer_id);
    document.getElementById("selVessel").value = state.selectedVesselId;
    document.getElementById("selCustomer").value = state.selectedCustomerId;

    // Also fill IMO input if it was missing
    const imoInp = document.getElementById("inp_imo");
    if (imoInp && (imoInp.value === "Não identificado" || imoInp.value === "[Não informado]" || !imoInp.value)) {
        imoInp.value = v.imo;
        onFieldManualEdit("imo");
    }

    updateDbMatchUI();
    showToast(`Vínculo confirmado pelo operador: ${v.vessel_name} (IMO ${v.imo}).`, "success");
}

function onVesselSelectChange() {
    const val = document.getElementById("selVessel").value;
    state.selectedVesselId = val;
    if (val) {
        const v = state.vessels.find(x => String(x.vessel_id) === String(val));
        if (v) {
            state.selectedCustomerId = String(v.customer_id);
            document.getElementById("selCustomer").value = state.selectedCustomerId;
        }
    }
    updateDbMatchUI();
}

function onCustomerSelectChange() {
    state.selectedCustomerId = document.getElementById("selCustomer").value;
    updateDbMatchUI();
}

function collectCurrentFormFields() {
    const allKeys = ["vessel_name", "imo", "port", "berth", "status", "eta", "etc", "voyage", "etb", "etd", "cargo", "notes"];
    const result = {};
    allKeys.forEach(k => {
        const inp = document.getElementById(`inp_${k}`);
        let val = inp ? inp.value.trim() : "";
        if (!val || val === "Não identificado" || val === "-") {
            val = "[Não informado]";
        }
        result[k] = val;
    });
    return result;
}

async function confirmRevision() {
    if (!state.selectedCustomerId) {
        showToast("Selecione um cliente destinatário antes de confirmar a revisão (BR11).", "warning");
        return;
    }

    const fields = collectCurrentFormFields();
    const savePermanent = document.getElementById("chkSavePermanent").checked;

    try {
        const res = await fetch("/api/review", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                processing_id: state.processingId,
                fields: fields,
                vessel_id: state.selectedVesselId || null,
                customer_id: state.selectedCustomerId,
                save_permanent: savePermanent
            })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.message || "Erro ao salvar revisão.", "error");
            return;
        }

        state.extraction.fields = data.fields;
        state.vessels = data.vessels;
        if (data.vessel_id) {
            state.selectedVesselId = String(data.vessel_id);
        }
        state.drafts = data.drafts;

        populateSelectDropdowns();
        renderHistoryAndDbTables();
        renderStep5EmailEditor();
        renderStep6Approval();

        if (data.permanent_saved) {
            showToast("Revisão confirmada e vínculo permanente salvo no banco de dados (CT12)!", "success");
        } else {
            showToast("Revisão confirmada! Minuta de e-mail gerada.", "success");
        }

        goToStep(5);
    } catch (err) {
        showToast("Erro ao salvar revisão no servidor.", "error");
    }
}

// ================= RENDER STEP 4: MANUAL VESSEL REGISTRATION =================
function openManualVesselRegistration() {
    renderStep4ManualRegistration();
    goToStep(4);
}

function renderStep4ManualRegistration() {
    const currentFields = state.extraction ? collectCurrentFormFields() : {};
    const nameVal = currentFields.vessel_name && currentFields.vessel_name !== "[Não informado]"
        ? currentFields.vessel_name
        : "MV Atlantic Star";
    const imoVal = currentFields.imo && currentFields.imo !== "[Não informado]"
        ? currentFields.imo
        : "";

    document.getElementById("regVesselName").value = nameVal;
    document.getElementById("regVesselImo").value = imoVal;
    if (state.selectedCustomerId) {
        document.getElementById("regVesselCustomer").value = state.selectedCustomerId;
    }
    validateManualImoInput();
}

function validateManualImoInput() {
    const imoInput = document.getElementById("regVesselImo");
    const icon = document.getElementById("regImoStatusIcon");
    const feedback = document.getElementById("regImoFeedbackText");
    const errSample = document.getElementById("regErrorCardSample");
    const errDesc = document.getElementById("regErrorCardDesc");
    const errTitle = document.getElementById("regErrorCardTitle");

    const val = (imoInput.value || "").trim();
    const isSevenDigits = /^\d{7}$/.test(val);
    const existingVessel = state.vessels.find(v => v.imo === val);

    if (isSevenDigits && !existingVessel) {
        imoInput.className = "form-control mono valid-input";
        icon.textContent = "✔";
        icon.style.color = "var(--sucesso)";
        feedback.style.color = "var(--sucesso)";
        feedback.textContent = "IMO válido: 7 dígitos numéricos e disponível.";

        errTitle.textContent = "Validação de Erro (Exemplo)";
        errSample.value = "93874";
        errDesc.textContent = "Erro: o número IMO deve conter exatamente 7 dígitos e não pode existir no banco.";
        return true;
    } else {
        imoInput.className = "form-control mono error-input";
        icon.textContent = "✖";
        icon.style.color = "var(--erro)";
        feedback.style.color = "var(--erro)";

        errTitle.textContent = "Validação de Erro (Detectado)";
        errSample.value = val || "(vazio)";

        if (existingVessel) {
            const msg = `Erro: IMO ${val} duplicado! Já pertence à embarcação "${existingVessel.vessel_name}".`;
            feedback.textContent = msg;
            errDesc.textContent = msg;
        } else {
            const msg = "Erro: o número IMO deve conter exatamente 7 dígitos numéricos e não pode existir no banco.";
            feedback.textContent = msg;
            errDesc.textContent = msg;
        }
        return false;
    }
}

async function submitNewVessel() {
    const vesselName = document.getElementById("regVesselName").value.trim();
    const imo = document.getElementById("regVesselImo").value.trim();
    const customerId = document.getElementById("regVesselCustomer").value;

    if (!vesselName) {
        showToast("Informe o nome da embarcação.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/vessels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                vessel_name: vesselName,
                imo: imo,
                customer_id: customerId,
                processing_id: state.processingId
            })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.message || "Não foi possível cadastrar a embarcação.", "error");
            validateManualImoInput();
            return;
        }

        state.vessels = data.vessels;
        state.imoMatch = data.vessel;
        state.selectedVesselId = String(data.vessel.vessel_id);
        state.selectedCustomerId = String(data.vessel.customer_id);

        // Update Step 3 inputs with the newly registered vessel
        document.getElementById("inp_vessel_name").value = data.vessel.vessel_name;
        document.getElementById("inp_imo").value = data.vessel.imo;
        onFieldManualEdit("vessel_name");
        onFieldManualEdit("imo");

        populateSelectDropdowns();
        document.getElementById("selVessel").value = state.selectedVesselId;
        document.getElementById("selCustomer").value = state.selectedCustomerId;
        updateDbMatchUI();
        renderHistoryAndDbTables();

        showToast(data.message, "success");
        goToStep(3);
    } catch (err) {
        showToast("Erro ao cadastrar embarcação no servidor.", "error");
    }
}

// ================= RENDER STEP 5: EMAIL EDITOR =================
function renderStep5EmailEditor() {
    if (!state.drafts) return;
    const langObj = state.drafts[state.currentLang] || state.drafts.en;

    document.getElementById("emailDestination").value = state.drafts.destination_email || "";
    document.getElementById("emailSubject").value = langObj.subject || "";
    document.getElementById("emailBody").value = langObj.body || "";

    document.getElementById("btnLangEn").classList.toggle("active", state.currentLang === "en");
    document.getElementById("btnLangPt").classList.toggle("active", state.currentLang === "pt");
}

function switchEmailLanguage(lang) {
    state.currentLang = lang;
    renderStep5EmailEditor();
    renderStep6Approval();
    const label = lang === "en" ? "Inglês (Internacional / Tech Shark Tank)" : "Português (Especificação MVP)";
    showToast(`Template alterado para: ${label}`, "success");
}

// ================= RENDER STEP 6: APPROVAL & SIMULATION =================
function renderStep6Approval() {
    const fields = state.extraction ? collectCurrentFormFields() : {};
    const customer = state.customers.find(c => String(c.customer_id) === String(state.selectedCustomerId));

    const destEmail = document.getElementById("emailDestination")?.value || state.drafts?.destination_email || "[Não definido]";
    const subject = document.getElementById("emailSubject")?.value || state.drafts?.[state.currentLang]?.subject || "";

    const opRows = [
        `<div class="summary-list-item"><strong>Embarcação:</strong> ${escapeHtml(fields.vessel_name || "[Não informado]")}</div>`,
        `<div class="summary-list-item"><strong>IMO:</strong> <span style="font-family:var(--font-mono);">${escapeHtml(fields.imo || "[Não informado]")}</span></div>`
    ];
    if (fields.voyage && fields.voyage !== "[Não informado]") {
        opRows.push(`<div class="summary-list-item"><strong>Viagem:</strong> ${escapeHtml(fields.voyage)}</div>`);
    }
    opRows.push(
        `<div class="summary-list-item"><strong>Porto / Berço:</strong> ${escapeHtml(fields.port || "[Não informado]")} — Berço ${escapeHtml(fields.berth || "[Não informado]")}</div>`,
        `<div class="summary-list-item"><strong>Status:</strong> ${escapeHtml(fields.status || "[Não informado]")}</div>`,
        `<div class="summary-list-item"><strong>Início / ETA:</strong> ${escapeHtml(fields.eta || "[Não informado]")}</div>`,
        `<div class="summary-list-item"><strong>Término / ETC:</strong> ${escapeHtml(fields.etc || "[Não informado]")}</div>`
    );
    if (fields.cargo && fields.cargo !== "[Não informado]") {
        opRows.push(`<div class="summary-list-item"><strong>Carga:</strong> ${escapeHtml(fields.cargo)}</div>`);
    }
    if (fields.notes && fields.notes !== "[Não informado]") {
        opRows.push(`<div class="summary-list-item"><strong>Observações:</strong> ${escapeHtml(fields.notes)}</div>`);
    }
    document.getElementById("approvalOperationSummary").innerHTML = opRows.join("");

    const commRows = [
        `<div class="summary-list-item"><strong>Cliente:</strong> ${escapeHtml(customer ? customer.company_name : "Não vinculado")}</div>`,
        `<div class="summary-list-item"><strong>Destinatário:</strong> <span style="font-family:var(--font-mono);">${escapeHtml(destEmail)}</span></div>`,
        `<div class="summary-list-item"><strong>Assunto:</strong> ${escapeHtml(subject)}</div>`,
        `<div class="summary-list-item"><strong>Responsável:</strong> ${escapeHtml(state.user.name)}</div>`
    ];
    document.getElementById("approvalCommSummary").innerHTML = commRows.join("");

    const banner = document.getElementById("approvalStatusBanner");
    if (state.approvalRecord) {
        banner.className = "badge badge-success";
        banner.innerHTML = `✔ Aprovado e envio simulado registrado em ${escapeHtml(state.approvalRecord.approval_date)} (ID #${state.approvalRecord.email_report_id})`;
    } else {
        banner.className = "badge badge-success";
        banner.textContent = "Pronto para aprovação e registro";
    }
}

async function copyFinalMessage() {
    const dest = document.getElementById("emailDestination").value.trim();
    const subj = document.getElementById("emailSubject").value.trim();
    const body = document.getElementById("emailBody").value;

    const fullText = `Para: ${dest}\nAssunto: ${subj}\n\n${body}`;
    try {
        await navigator.clipboard.writeText(fullText);
        showToast("Mensagem copiada para a área de transferência com todas as alterações (RF12 / CT17)!", "success");
    } catch (e) {
        // Fallback copy
        const ta = document.createElement("textarea");
        ta.value = fullText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        showToast("Mensagem copiada para a área de transferência (CT17)!", "success");
    }
}

async function approveAndSimulateSend(actionType) {
    const dest = document.getElementById("emailDestination").value.trim();
    const subj = document.getElementById("emailSubject").value.trim();
    const body = document.getElementById("emailBody").value.trim();

    if (!dest) {
        showToast("Informe o e-mail do destinatário antes de aprovar (BR14). Volte à Etapa 3 ou 5.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                processing_id: state.processingId,
                destination_email: dest,
                email_subject: subj,
                email_body: body
            })
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
            showToast(data.message || "Falha ao registrar aprovação.", "error");
            return;
        }

        state.approvalRecord = data.report;
        state.history = data.history;

        renderStep6Approval();
        renderHistoryAndDbTables();

        const msg = actionType === "simulate"
            ? `Envio simulado concluído para ${dest}! Aprovação registrada no banco (RN08 / CT15).`
            : `Relatório aprovado por ${state.user.name} e registrado na tabela Email_Report (CT15 / CT16)!`;
        showToast(msg, "success");
    } catch (err) {
        showToast("Erro ao registrar aprovação no servidor.", "error");
    }
}

// ================= RENDER STEP 7: HISTORY & DB TABLES =================
function renderHistoryAndDbTables() {
    const histBody = document.getElementById("historyTableBody");
    const countBadge = document.getElementById("historyCountBadge");
    if (countBadge) {
        countBadge.textContent = `${state.history.length} registro${state.history.length !== 1 ? "s" : ""}`;
    }

    if (histBody) {
        if (state.history.length === 0) {
            histBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--texto-secundario); padding:24px;">Nenhuma comunicação aprovada ainda. Conclua a Etapa 6 para registrar no histórico.</td></tr>`;
        } else {
            histBody.innerHTML = state.history.map(h => {
                const vName = h.db_vessel_name || h.extracted_data?.vessel_name || "[Não informado]";
                const vImo = h.db_imo || h.extracted_data?.imo || "-";
                const cName = h.db_company_name || "Cliente";
                return `
                    <tr>
                        <td style="font-family:var(--font-mono); font-weight:700;">#${h.email_report_id}</td>
                        <td style="font-family:var(--font-mono); font-size:12.5px;">${escapeHtml(h.approval_date)}</td>
                        <td><strong>${escapeHtml(h.approving_user_name)}</strong><br><span style="font-size:11.5px; color:var(--texto-secundario);">${escapeHtml(h.approving_user_role)}</span></td>
                        <td style="font-family:var(--font-mono); font-size:12.5px;">${escapeHtml(h.original_file_name)}</td>
                        <td><strong>${escapeHtml(vName)}</strong><br><span style="font-family:var(--font-mono); font-size:12px; color:var(--texto-secundario);">IMO ${escapeHtml(vImo)}</span></td>
                        <td><strong>${escapeHtml(cName)}</strong><br><span style="font-family:var(--font-mono); font-size:12px; color:var(--sucesso);">${escapeHtml(h.destination_email)}</span></td>
                        <td>${escapeHtml(h.email_subject)}</td>
                        <td>
                            <button class="btn btn-outline-subtle btn-sm" onclick="viewHistoryEmailModal(${h.email_report_id})">
                                👁 Ver Mensagem
                            </button>
                        </td>
                    </tr>
                `;
            }).join("");
        }
    }

    const vesselsBody = document.getElementById("vesselsTableBody");
    if (vesselsBody) {
        vesselsBody.innerHTML = state.vessels.map(v => `
            <tr>
                <td style="font-family:var(--font-mono);">#${v.vessel_id}</td>
                <td><strong>${escapeHtml(v.vessel_name)}</strong></td>
                <td><span class="badge badge-neutral">${escapeHtml(v.imo)}</span></td>
                <td>${escapeHtml(v.company_name)}</td>
            </tr>
        `).join("");
    }

    const customersBody = document.getElementById("customersTableBody");
    if (customersBody) {
        customersBody.innerHTML = state.customers.map(c => `
            <tr>
                <td style="font-family:var(--font-mono);">#${c.customer_id}</td>
                <td><strong>${escapeHtml(c.company_name)}</strong></td>
                <td>${escapeHtml(c.contact_name || "-")}</td>
                <td style="font-family:var(--font-mono); font-size:12.5px; color:var(--sucesso);">${escapeHtml(c.destination_email)}</td>
            </tr>
        `).join("");
    }

    const usersBody = document.getElementById("usersTableBody");
    if (usersBody && state.users) {
        usersBody.innerHTML = state.users.map(u => `
            <tr>
                <td style="font-family:var(--font-mono);">#${u.user_id}</td>
                <td><strong>${escapeHtml(u.name)}</strong></td>
                <td>${escapeHtml(u.role)}</td>
                <td><span class="badge badge-neutral">${escapeHtml(u.username || "-")}</span></td>
                <td style="font-family:var(--font-mono); font-size:12.5px; color:var(--destaque);">${escapeHtml(u.email || "-")}</td>
            </tr>
        `).join("");
    }
}

function viewHistoryEmailModal(reportId) {
    const item = state.history.find(h => h.email_report_id === reportId);
    if (!item) return;
    alert(
        `REGISTRO DE APROVAÇÃO #${item.email_report_id}\n` +
        `Aprovado por: ${item.approving_user_name} (${item.approving_user_role})\n` +
        `Data/Hora: ${item.approval_date}\n` +
        `Destinatário: ${item.destination_email}\n` +
        `Assunto: ${item.email_subject}\n` +
        `----------------------------------------\n\n` +
        `${item.email_body}`
    );
}

// ================= NAVIGATION BETWEEN STEPS =================
function goToStep(stepNumber) {
    state.currentStep = stepNumber;

    // Update sidebar active state
    document.querySelectorAll(".nav-item").forEach(btn => {
        const s = Number(btn.getAttribute("data-step"));
        btn.classList.toggle("active", s === stepNumber);
    });

    // Update active panel
    document.querySelectorAll(".step-panel").forEach(panel => {
        panel.classList.remove("active");
    });
    const target = document.getElementById(`step-${stepNumber}`);
    if (target) target.classList.add("active");

    if (stepNumber === 6) {
        renderStep6Approval();
    } else if (stepNumber === 7) {
        renderHistoryAndDbTables();
    }

    updateHeaderForStep(stepNumber);
}

function updateHeaderForStep(step, customPendingCount = null) {
    const titleEl = document.getElementById("headerTitle");
    const subEl = document.getElementById("headerSubtitle");
    const actEl = document.getElementById("headerActions");

    const fileName = state.fileInfo ? state.fileInfo.filename : "BOLETIM_ATLANTIC_STAR_1911.pdf";
    const pendingCount = customPendingCount !== null
        ? customPendingCount
        : (state.extraction ? state.extraction.summary.pending : 1);

    if (step === 1) {
        titleEl.textContent = "Upload de Boletim Operacional";
        subEl.textContent = "Etapa 1 de 6 • Importação e validação do documento PDF";
        actEl.innerHTML = `<span class="badge badge-success">🛡 Limite: PDF até 5 MB</span>`;
    } else if (step === 2) {
        titleEl.textContent = "Dados Extraídos Automaticamente";
        subEl.textContent = `Etapa 2 de 6 • Origem: ${fileName}`;
        actEl.innerHTML = `<button class="btn btn-primary" onclick="goToStep(3)">Prosseguir para revisão →</button>`;
    } else if (step === 3) {
        titleEl.textContent = "Revisão e Vínculo Operacional";
        subEl.textContent = "Etapa 3 de 6 • Edite campos extraídos e associe embarcação e cliente";
        if (pendingCount > 0) {
            actEl.innerHTML = `<span class="badge badge-warning">⚠ ${pendingCount} campo${pendingCount > 1 ? "s" : ""} requer${pendingCount > 1 ? "em" : ""} atenção</span>`;
        } else {
            actEl.innerHTML = `<span class="badge badge-success">✔ Todos os campos preenchidos</span>`;
        }
    } else if (step === 4) {
        titleEl.textContent = "Cadastro Manual de Embarcação";
        subEl.textContent = "Etapa 4 de 6 • Registro de nova embarcação não encontrada no banco";
        actEl.innerHTML = `<span class="badge badge-neutral">Tabela: Vessel (IMO UNIQUE)</span>`;
    } else if (step === 5) {
        titleEl.textContent = "Editor de E-mail Operacional";
        subEl.textContent = state.currentLang === "en"
            ? "Etapa 5 de 6 • Minuta automática em inglês totalmente editável"
            : "Etapa 5 de 6 • Minuta automática em português totalmente editável";
        actEl.innerHTML = `<span class="badge badge-success" style="background:var(--destaque-light); color:var(--destaque);">✎ Todos os campos editáveis</span>`;
    } else if (step === 6) {
        titleEl.textContent = "Aprovação Final e Envio Simulado";
        subEl.textContent = "Etapa 6 de 6 • Conferência final e registro de rastreabilidade";
        actEl.innerHTML = `<span class="badge badge-success">👤 Aprovador: ${escapeHtml(state.user.name)}</span>`;
    } else if (step === 7) {
        titleEl.textContent = "Histórico de Aprovações e Banco de Dados";
        subEl.textContent = "Rastreabilidade completa das comunicações aprovadas (RN10 / CT16) e tabelas do modelo ERD";
        actEl.innerHTML = `<span class="badge badge-neutral">SQLite • 5 Entidades ERD</span>`;
    }
}

// ================= UTILITIES =================
function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "success" ? "✔" : (type === "error" ? "✖" : "⚠");
    toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.25s ease";
        setTimeout(() => toast.remove(), 260);
    }, 3800);
}

function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
