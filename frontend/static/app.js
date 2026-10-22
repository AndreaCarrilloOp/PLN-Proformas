let currentRequest = null;
let currentQuote = null;
let currentEmail = null;
let currentProviderRequest = null;
let providerRequests = [];
let emailDrafts = [];
let selectedEmailId = null;
let initialConversationHtml = "";
let quoteRecords = [];
let catalogProducts = [];
let catalogProviders = [];
let toastTimer = null;
let currentEmailStep = 1;
let maxEmailStep = 1;
let validationCorrectionMode = null;
let lastValidationPromptKey = null;
let completionAnnouncedForRequest = null;

const $ = (id) => document.getElementById(id);

const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

function autoGrowTextarea(element) {
  if (!element) return;
  element.style.height = "auto";
  const maxHeight = Number.parseInt(getComputedStyle(element).maxHeight, 10) || 180;
  element.style.height = `${Math.min(element.scrollHeight, maxHeight)}px`;
}

function skeletonRows(count = 3) {
  return Array.from({ length: count }, () => '<div class="skeleton-row" aria-hidden="true"></div>').join("");
}

const screenTitles = {
  request: "Nueva solicitud",
  validation: "Detalle de la solicitud",
  providers: "Correos",
  quotes: "Proformas",
  catalog: "Catálogo",
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    window.location.replace("/login");
    throw new Error("La sesión expiró. Inicie sesión nuevamente.");
  }
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

async function loadSessionUser() {
  const data = await api("/api/auth/me");
  const user = data.usuario || {};
  const label = $("sessionUserName");
  if (label) label.textContent = user.nombre || user.username || "Usuario";
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.replace("/login");
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[c]);
}

function normalizeStatus(value) {
  const status = String(value || "").toUpperCase();
  if (["COMPLETO", "VALIDADA", "AUTORIZADO", "ENVIADO"].includes(status)) return "complete";
  if (["REQUIERE_CONFIRMACION", "PRELIMINAR"].includes(status)) return "warning";
  if (["ERROR", "RECHAZADO"].includes(status)) return "error";
  return "pending";
}

function humanStatus(value) {
  const status = String(value || "").toUpperCase();
  const labels = {
    PENDIENTE: "FALTAN DATOS",
    REQUIERE_CONFIRMACION: "NECESITA CONFIRMACIÓN",
    COMPLETO: "LISTO",
    PRELIMINAR: "POR REVISAR",
  };
  return labels[status] || status || "SIN ESTADO";
}

function statusBadge(value) {
  return `<span class="badge ${normalizeStatus(value)}">${escapeHtml(humanStatus(value))}</span>`;
}

function showToast(message, isError = false) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = "toast"; }, 3200);
}

function handleError(error) {
  console.error(error);
  showToast(error.message || "Ocurrió un error inesperado.", true);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-CR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function setRequestStatus(value) {
  const badge = $("requestStatus");
  badge.textContent = value === "Sin solicitud" ? value : humanStatus(value);
  badge.className = `status-chip ${value === "Sin solicitud" ? "neutral" : normalizeStatus(value)}`;
}

function setItemsContent(html, empty = false) {
  const items = $("items");
  items.className = empty ? "result-stack empty-state large-empty" : "result-stack";
  items.innerHTML = html;
}

function setProvidersContent(html, empty = false) {
  const providers = $("providers");
  if (!providers) return;
  providers.className = empty ? "result-stack empty-state compact-empty" : "result-stack";
  providers.innerHTML = html;
}

function requestSummaryHtml(req, compact = false) {
  if (!req) return '<span class="muted-copy">No hay una solicitud seleccionada.</span>';
  const items = req.articulos || [];
  return `
    <div class="context-main">
      <div>
        <span class="context-label">Solicitud #${req.id}</span>
        <strong>${escapeHtml(req.texto_original)}</strong>
      </div>
      ${statusBadge(req.estado)}
    </div>
    ${compact ? "" : `<div class="context-meta"><span>${items.length} artículo(s)</span></div>`}
  `;
}

function updateRequestContext() {
  const context = $("activeRequestContext");
  if (!currentRequest) {
    context.textContent = "Sin solicitud activa";
    context.className = "request-context";
    $("providerRequestSummary").innerHTML = "No hay una solicitud completa seleccionada.";
    $("comparisonRequestSummary").innerHTML = "Seleccione una solicitud para consultar su comparación.";
    renderSelectedQuoteRequest(null);
    return;
  }

  context.textContent = `Solicitud #${currentRequest.id} · ${humanStatus(currentRequest.estado)}`;
  context.className = `request-context ${normalizeStatus(currentRequest.estado)}`;
  $("providerRequestSummary").classList.remove("muted-context");
  $("providerRequestSummary").innerHTML = requestSummaryHtml(currentRequest);
  $("comparisonRequestSummary").classList.remove("muted-context");
  $("comparisonRequestSummary").innerHTML = requestSummaryHtml(currentRequest, true);
  renderSelectedQuoteRequest(currentRequest);
}

function renderSelectedQuoteRequest(req) {
  const panel = $("selectedQuoteRequest");
  if (!req) {
    panel.className = "selected-request-panel muted-selected";
    panel.innerHTML = `
      <div>
        <h2>Ninguna solicitud seleccionada</h2>
        <p>Busque una solicitud para continuar.</p>
      </div>`;
    return;
  }
  panel.className = "selected-request-panel";
  panel.innerHTML = `
    <div>
      <span class="context-label">Solicitud #${req.id}</span>
      <h2>${escapeHtml(req.texto_original)}</h2>
      <p>${req.articulos.length} artículo(s)</p>
    </div>
    ${statusBadge(req.estado)}
  `;
}

function renderRequest(req) {
  currentRequest = req;
  setRequestStatus(req.estado);
  $("providersBtn").disabled = req.estado !== "COMPLETO";
  $("goToProvidersBtn").disabled = req.estado !== "COMPLETO";
  $("uploadPdfBtn").disabled = false;
  $("comparisonBtn").disabled = false;
  updateRequestContext();

  const html = req.articulos.map((item, idx) => `
    <article class="item">
      <div class="row">
        <div>
          <span class="item-index">Artículo ${idx + 1}</span>
          <h3>${escapeHtml(item.producto ?? "Producto por confirmar")}</h3>
        </div>
        ${statusBadge(item.estado)}
      </div>

      <div class="grid">
        <div class="kv"><span>Fragmento original</span><strong>${escapeHtml(item.fragmento_original)}</strong></div>
        <div class="kv"><span>Producto</span><strong>${escapeHtml(item.producto ?? "No definido")}</strong></div>
        <div class="kv"><span>Cantidad</span><strong>${escapeHtml(item.cantidad ?? "No definida")}</strong></div>
        <div class="kv"><span>Marca</span><strong>${escapeHtml(item.marca ?? "No indicada")}</strong></div>
      </div>

      ${item.caracteristicas.length ? `
        <div class="detected-block">
          <p><strong>Características detectadas</strong></p>
          <ul>${item.caracteristicas.map((c) => `<li>${escapeHtml(c.name)}: <strong>${escapeHtml(c.normalized_value)}</strong> <small>(${escapeHtml(c.source)})</small></li>`).join("")}</ul>
        </div>
      ` : ""}

      ${item.transformaciones.filter((t) => !t.resolved).map((t) => `
        <div class="transform">
          <strong>Interpretación por confirmar</strong><br>
          ${escapeHtml(t.original_value)} → ${escapeHtml(t.normalized_value ?? "sin normalizar")}<br>
          <small>${escapeHtml(t.note ?? t.source)}</small>
          <div class="inline">
            <button type="button" onclick="confirmTransform(${t.id}, true)">Aceptar sugerencia</button>
            <button type="button" class="secondary" onclick="rejectTransform(${t.id})">Rechazar/corregir</button>
          </div>
        </div>
      `).join("")}

      ${item.preguntas.filter((q) => q.status === "PENDIENTE").map((q) => `
        <div class="question">
          <strong>${escapeHtml(q.question_text)}</strong>
          <div class="inline">
            <input id="answer-${q.id}" placeholder="Escriba la respuesta">
            <button type="button" onclick="answerQuestion(${q.id})">Guardar respuesta</button>
          </div>
        </div>
      `).join("")}
    </article>
  `).join("");

  setItemsContent(html || '<p class="table-empty">No se detectaron artículos.</p>');
}

window.answerQuestion = async (questionId) => {
  try {
    const input = $(`answer-${questionId}`);
    const respuesta = input.value.trim();
    if (!respuesta) {
      showToast("Escriba una respuesta antes de guardarla.", true);
      input.focus();
      return;
    }
    const req = await api(`/api/solicitudes/${currentRequest.id}/respuestas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta_id: questionId, respuesta }),
    });
    renderRequest(req);
    showToast("Respuesta guardada.");
  } catch (e) { handleError(e); }
};

window.confirmTransform = async (id, confirmado) => {
  try {
    const req = await api(`/api/solicitudes/${currentRequest.id}/confirmaciones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transformacion_id: id, confirmado }),
    });
    renderRequest(req);
    showToast("Interpretación confirmada.");
  } catch (e) { handleError(e); }
};

window.rejectTransform = async (id) => {
  const correction = prompt("Puede indicar un valor corregido o dejarlo vacío para rechazar la sugerencia:", "");
  if (correction === null) return;
  try {
    const req = await api(`/api/solicitudes/${currentRequest.id}/confirmaciones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transformacion_id: id,
        confirmado: false,
        valor_corregido: correction || null,
      }),
    });
    renderRequest(req);
    showToast("Interpretación actualizada.");
  } catch (e) { handleError(e); }
};

function showScreen(name) {
  if (!screenTitles[name]) return;
  document.querySelectorAll("[data-screen-view]").forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screenView === name);
  });
  document.querySelectorAll(".nav-item[data-screen]").forEach((item) => {
    const isActive = item.dataset.screen === name;
    item.classList.toggle("active", isActive);
    if (isActive) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  $("screenTitle").textContent = screenTitles[name];
  window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  if (window.innerWidth <= 720) $("sidebar").classList.remove("open");

  if (name === "quotes" && currentRequest) {
    renderSelectedQuoteRequest(currentRequest);
    Promise.all([
      loadQuoteHistory(currentRequest.id),
      refreshComparison(),
    ]).catch(handleError);
  }
}

function scrollChatToLatest(behavior = "smooth") {
  const conversation = $("conversation");
  if (!conversation) return;
  requestAnimationFrame(() => {
    conversation.scrollTo({
      top: conversation.scrollHeight,
      behavior: reduceMotion ? "auto" : behavior,
    });
  });
}

function appendUserMessage(text) {
  const conversation = $("conversation");
  const message = document.createElement("article");
  message.className = "chat-message user-message";
  message.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
  conversation.appendChild(message);
  scrollChatToLatest();
}

function appendAssistantMessage(content, className = "") {
  const conversation = $("conversation");
  const message = document.createElement("article");
  message.className = "chat-message assistant-message";
  message.innerHTML = `
    <div class="chat-avatar" aria-hidden="true">A</div>
    <div class="chat-bubble ${className}">${content}</div>`;
  conversation.appendChild(message);
  scrollChatToLatest();
}

function getValidationTasks(req = currentRequest) {
  if (!req) return [];
  const tasks = [];
  req.articulos.forEach((item, itemIndex) => {
    item.transformaciones
      .filter((transformation) => !transformation.resolved)
      .forEach((transformation) => tasks.push({
        type: "confirmation",
        item,
        itemIndex,
        data: transformation,
      }));
    item.preguntas
      .filter((question) => question.status === "PENDIENTE")
      .forEach((question) => tasks.push({
        type: "question",
        item,
        itemIndex,
        data: question,
      }));
  });
  return tasks;
}

function taskKey(task) {
  if (!task) return null;
  return `${task.type}:${task.data.id}`;
}

function itemLabel(task) {
  const quantity = task.item.cantidad ?? "?";
  const product = task.item.producto ?? "producto por confirmar";
  const brand = task.item.marca ? ` ${task.item.marca}` : "";
  return `${quantity} × ${product}${brand}`;
}

function fieldExample(fieldKey) {
  const hints = {
    ram: "Ej. 16 GB",
    almacenamiento: "Ej. 512 GB SSD",
    procesador: "Ej. Intel Core i7",
    tamano_pantalla: "Ej. 27 pulgadas",
    cantidad: "Ej. 5",
    producto: "Ej. laptop o monitor",
    marca: "Ej. Dell",
  };
  return hints[fieldKey] || "Escriba la información solicitada";
}

function pendingDescription(req = currentRequest) {
  const tasks = getValidationTasks(req);
  const questions = tasks.filter((task) => task.type === "question").length;
  const confirmations = tasks.filter((task) => task.type === "confirmation").length;
  const parts = [];
  if (questions) parts.push(`${questions} dato${questions === 1 ? "" : "s"} por completar`);
  if (confirmations) parts.push(`${confirmations} interpretación${confirmations === 1 ? "" : "es"} por confirmar`);
  return parts.join(" y ");
}

function updateChatComposerMode() {
  const input = $("requestText");
  const button = $("analyzeBtn");
  const task = getValidationTasks()[0];

  input.disabled = false;
  button.disabled = false;

  if (!currentRequest) {
    input.placeholder = "Escriba lo que necesita cotizar…";
    button.querySelector("span:first-child").textContent = "Enviar";
    return;
  }

  if (validationCorrectionMode) {
    input.placeholder = "Escriba el valor correcto…";
    button.querySelector("span:first-child").textContent = "Responder";
    return;
  }

  if (task?.type === "question") {
    input.placeholder = fieldExample(task.data.field_key);
    button.querySelector("span:first-child").textContent = "Responder";
    return;
  }

  if (task?.type === "confirmation") {
    input.placeholder = "Puede responder sí, no o escribir el valor correcto…";
    button.querySelector("span:first-child").textContent = "Responder";
    return;
  }

  input.placeholder = "Solicitud completa. Use “Nueva solicitud” para iniciar otra.";
  input.disabled = true;
  button.disabled = true;
  button.querySelector("span:first-child").textContent = "Listo";
}

function conversationalItemSummary(item) {
  const quantity = item.cantidad ?? "?";
  const product = item.producto ?? "producto por confirmar";
  const brand = item.marca ? ` ${item.marca}` : "";
  const features = (item.caracteristicas || [])
    .map((feature) => feature.normalized_value)
    .filter(Boolean)
    .slice(0, 3);
  return `
    <li>
      <strong>${escapeHtml(`${quantity} × ${product}${brand}`)}</strong>
      ${features.length ? `<span>${features.map(escapeHtml).join(" · ")}</span>` : ""}
    </li>`;
}

function validationPromptMarkup(task) {
  if (!task) return "";
  const context = `<span class="conversation-context">${escapeHtml(itemLabel(task))}</span>`;
  if (task.type === "confirmation") {
    const suggestion = task.data.normalized_value || "la interpretación sugerida";
    return `
      ${context}
      <strong>¿Quiso decir ${escapeHtml(suggestion)}?</strong>
      <p>Escribió <b>${escapeHtml(task.data.original_value)}</b>. Responda <b>sí</b> para confirmarlo o escriba el valor correcto.</p>`;
  }
  return `
    ${context}
    <strong>${escapeHtml(task.data.question_text)}</strong>`;
}

function renderChatAnalysis(req, originalText) {
  appendUserMessage(originalText);
  const pending = pendingDescription(req);
  const task = getValidationTasks(req)[0];
  const summary = `
    <ul class="conversation-summary-list">
      ${req.articulos.map(conversationalItemSummary).join("")}
    </ul>`;

  if (task) {
    lastValidationPromptKey = taskKey(task);
    completionAnnouncedForRequest = null;
    appendAssistantMessage(`
      <p>${pending ? `Entendí la solicitud. Antes de continuar necesito ${escapeHtml(pending)}.` : "Entendí la solicitud."}</p>
      ${summary}
      <div class="conversation-next-question">
        ${validationPromptMarkup(task)}
      </div>`, "analysis-bubble simplified-analysis");
    updateChatComposerMode();
    return;
  }

  completionAnnouncedForRequest = req.id;
  appendAssistantMessage(`
    <strong>La solicitud está lista.</strong>
    ${summary}
    <div class="chat-response-actions completion-actions">
      <button type="button" class="primary-action" onclick="continueToProvidersFromChat()">Preparar correos</button>
    </div>`, "analysis-bubble simplified-analysis complete-conversation");
  updateChatComposerMode();
}

function promptNextValidationTask() {
  if (!currentRequest) {
    updateChatComposerMode();
    return;
  }

  const task = getValidationTasks(currentRequest)[0];
  if (!task) {
    updateChatComposerMode();
    if (currentRequest.estado === "COMPLETO" && completionAnnouncedForRequest !== currentRequest.id) {
      completionAnnouncedForRequest = currentRequest.id;
      appendAssistantMessage(`
        <strong>Listo, la solicitud está completa.</strong>
        <p>Ya puede preparar los correos para los proveedores compatibles.</p>
        <div class="chat-response-actions completion-actions">
          <button type="button" class="primary-action" onclick="continueToProvidersFromChat()">Preparar correos</button>
        </div>`, "complete-conversation");
    }
    return;
  }

  const key = taskKey(task);
  if (lastValidationPromptKey === key && !validationCorrectionMode) {
    updateChatComposerMode();
    return;
  }
  lastValidationPromptKey = key;
  updateChatComposerMode();

  if (validationCorrectionMode) {
    appendAssistantMessage(`
      <span class="conversation-context">${escapeHtml(itemLabel(task))}</span>
      <strong>¿Cuál es el valor correcto?</strong>`, "validation-question-bubble");
    return;
  }

  appendAssistantMessage(validationPromptMarkup(task), "validation-question-bubble");
}

function isValidationHelpQuestion(text) {
  const normalized = text.trim().toLowerCase();
  if (!normalized.includes("?") && !/^(qué|que|por qué|porque|cómo|como)\b/.test(normalized)) return false;
  return /(pendiente|falta|faltan|estado|significa|validaci[oó]n|por confirmar)/.test(normalized);
}

function explainCurrentValidation() {
  const task = getValidationTasks()[0];
  if (!task) return;
  const pending = pendingDescription(currentRequest);
  const currentPrompt = task.type === "question"
    ? task.data.question_text
    : `confirmar si “${task.data.original_value}” corresponde a “${task.data.normalized_value ?? "la sugerencia"}”`;
  appendAssistantMessage(`
    <strong>Seguimos con la misma solicitud.</strong>
    <p>Todavía falta ${escapeHtml(pending)}. Ahora necesito ${escapeHtml(currentPrompt)}.</p>`, "validation-help-bubble");
  lastValidationPromptKey = null;
  promptNextValidationTask();
}

async function processValidationMessage(text) {
  const task = getValidationTasks()[0];
  if (!task) return;

  appendUserMessage(text);

  if (isValidationHelpQuestion(text) && !validationCorrectionMode) {
    explainCurrentValidation();
    return;
  }

  try {
    let req;
    if (task.type === "confirmation") {
      const normalized = text.trim().toLowerCase().replace(/[.!]+$/g, "");
      const positive = ["si", "sí", "correcto", "correcta", "confirmo", "exacto", "exactamente"].includes(normalized);
      const negative = ["no", "incorrecto", "incorrecta"].includes(normalized);

      if (validationCorrectionMode || (!positive && !negative)) {
        req = await api(`/api/solicitudes/${currentRequest.id}/confirmaciones`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transformacion_id: task.data.id,
            confirmado: false,
            valor_corregido: text.trim(),
          }),
        });
        validationCorrectionMode = null;
      } else if (positive) {
        req = await api(`/api/solicitudes/${currentRequest.id}/confirmaciones`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transformacion_id: task.data.id, confirmado: true }),
        });

      } else {
        validationCorrectionMode = { transformationId: task.data.id };
        lastValidationPromptKey = taskKey(task);
        appendAssistantMessage(`
          <span class="conversation-context">${escapeHtml(itemLabel(task))}</span>
          <strong>¿Cuál es el valor correcto?</strong>`, "validation-question-bubble");
        updateChatComposerMode();
        return;
      }
    } else {
      req = await api(`/api/solicitudes/${currentRequest.id}/respuestas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta_id: task.data.id, respuesta: text }),
      });

    }

    renderRequest(req);
    lastValidationPromptKey = null;
    promptNextValidationTask();
  } catch (error) {
    handleError(error);
    appendAssistantMessage(`
      <strong>No pude guardar esa respuesta todavía.</strong>
      <p>${escapeHtml(error.message || "Revise la información e inténtelo nuevamente.")}</p>`, "validation-error-bubble");
    lastValidationPromptKey = null;
    promptNextValidationTask();
  }
}

window.continueToProvidersFromChat = () => {
  if (!currentRequest || currentRequest.estado !== "COMPLETO") return;
  setEmailStep(1);
  showScreen("providers");
};

async function submitConversationMessage() {
  const text = $("requestText").value.trim();
  if (!text) {
    showToast("Escriba un mensaje antes de enviarlo.", true);
    $("requestText").focus();
    return;
  }

  const button = $("analyzeBtn");
  const previous = button.innerHTML;
  button.disabled = true;
  button.innerHTML = '<span>Procesando…</span><span class="send-arrow" aria-hidden="true">…</span>';

  try {
    if (currentRequest && getValidationTasks().length) {
      $("requestText").value = "";
      autoGrowTextarea($("requestText"));
      await processValidationMessage(text);
      $("requestText").focus();
      return;
    }

    if (currentRequest?.estado === "COMPLETO") {
      showToast("La solicitud actual ya está completa. Use “Nueva solicitud” para iniciar otra.", true);
      return;
    }

    const req = await api("/api/solicitudes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: text }),
    });
    renderRequest(req);
    resetEmailWorkflow(false);
    $("requestText").value = "";
    autoGrowTextarea($("requestText"));
    renderChatAnalysis(req, text);
    showToast("Solicitud analizada.");
  } catch (error) {
    handleError(error);
  } finally {
    button.innerHTML = previous;
    updateChatComposerMode();
    $("requestText").focus();
  }
}

$("analyzeBtn").addEventListener("click", submitConversationMessage);
$("requestText").addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    submitConversationMessage();
  }
});

$("goToProvidersBtn").addEventListener("click", () => {
  if (!currentRequest || currentRequest.estado !== "COMPLETO") return;
  setEmailStep(1);
  showScreen("providers");
});

function updateEmailStepper() {
  document.querySelectorAll(".stepper-step[data-email-step]").forEach((step) => {
    const number = Number(step.dataset.emailStep);
    step.disabled = number > maxEmailStep;
    const isActive = number === currentEmailStep;
    step.classList.toggle("active", isActive);
    step.classList.toggle("complete", number < currentEmailStep && number <= maxEmailStep);
    if (isActive) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  document.querySelectorAll(".step-line").forEach((line, index) => {
    line.classList.toggle("complete", index + 1 < currentEmailStep);
  });
}

function setEmailStep(step) {
  if (step > maxEmailStep) return;
  currentEmailStep = step;
  document.querySelectorAll(".email-flow-stage").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `email-step-${step}`);
  });
  if (step === 2) renderEmailDraftWorkspace();
  if (step === 3) renderApprovalList();
  if (step === 4) renderSendList();
  updateEmailStepper();
}

function unlockEmailStep(step) {
  maxEmailStep = Math.max(maxEmailStep, step);
  updateEmailStepper();
}

function resetEmailWorkflow(clearProviders = true) {
  currentEmail = null;
  currentProviderRequest = null;
  selectedEmailId = null;
  emailDrafts = [];
  if (clearProviders) providerRequests = [];
  currentEmailStep = 1;
  maxEmailStep = 1;
  if ($("emailDraftList")) $("emailDraftList").innerHTML = "";
  if ($("emailDraftCount")) $("emailDraftCount").textContent = "0";
  if ($("emailComposerPanel")) $("emailComposerPanel").innerHTML = `
    <div class="empty-mail-composer"><div class="empty-icon" aria-hidden="true">✉</div><h2>Seleccione un correo</h2></div>`;
  if ($("emailApprovalList")) $("emailApprovalList").innerHTML = "";
  if ($("emailApprovalSummary")) $("emailApprovalSummary").innerHTML = "";
  if ($("emailSendList")) $("emailSendList").innerHTML = "";
  if ($("emailSendSummary")) $("emailSendSummary").innerHTML = "";
  if ($("goToApprovalBtn")) $("goToApprovalBtn").disabled = true;
  if ($("goToSendBtn")) $("goToSendBtn").disabled = true;
  updateEmailStepper();
  setEmailStep(1);
}

function mergeEmailRecord(record) {
  const index = emailDrafts.findIndex((email) => email.id === record.id);
  const providerRequest = providerRequests.find((row) => row.id === record.solicitud_proveedor_id);
  const merged = {
    ...(index >= 0 ? emailDrafts[index] : {}),
    ...record,
    articulos: providerRequest?.articulos || (index >= 0 ? emailDrafts[index].articulos : []),
    articulos_no_incluidos: providerRequest?.articulos_no_incluidos || (index >= 0 ? emailDrafts[index].articulos_no_incluidos : []),
    cobertura: providerRequest?.cobertura || (index >= 0 ? emailDrafts[index].cobertura : "PARCIAL"),
    articulos_incluidos: providerRequest?.articulos_incluidos ?? (index >= 0 ? emailDrafts[index].articulos_incluidos : 0),
    articulos_totales: providerRequest?.articulos_totales ?? (index >= 0 ? emailDrafts[index].articulos_totales : 0),
  };
  if (index >= 0) emailDrafts[index] = merged;
  else emailDrafts.push(merged);
  return merged;
}

async function prepareAllEmailDrafts(rows) {
  const drafts = await Promise.all(rows.map(async (providerRequest) => {
    const email = await api(`/api/solicitudes-proveedor/${providerRequest.id}/correo/borrador`, { method: "POST" });
    return {
      ...email,
      articulos: providerRequest.articulos,
      articulos_no_incluidos: providerRequest.articulos_no_incluidos || [],
      cobertura: providerRequest.cobertura,
      articulos_incluidos: providerRequest.articulos_incluidos,
      articulos_totales: providerRequest.articulos_totales,
    };
  }));
  emailDrafts = drafts;
  selectedEmailId = drafts[0]?.id ?? null;
  $("emailDraftCount").textContent = String(drafts.length);
  $("goToApprovalBtn").disabled = !drafts.length;
  renderEmailDraftWorkspace();
}

function renderEmailDraftWorkspace() {
  const list = $("emailDraftList");
  if (!list) return;
  if (!emailDrafts.length) {
    list.innerHTML = '<div class="mail-list-empty">No hay correos preparados.</div>';
    return;
  }

  list.innerHTML = emailDrafts.map((email) => `
    <button type="button" class="mail-list-item ${email.id === selectedEmailId ? "active" : ""}" onclick="openEmailComposer(${email.id})">
      <div class="mail-list-item-top"><strong>${escapeHtml(email.proveedor || "Proveedor")}</strong>${statusBadge(email.estado)}</div>
      <span>${escapeHtml(email.destinatario)}</span>
      <small>${escapeHtml(email.asunto)}</small>
      <span class="coverage-inline ${String(email.cobertura || "PARCIAL").toLowerCase()}">${email.cobertura === "TOTAL" ? "Todos los artículos" : "Solo artículos compatibles"} · ${email.articulos_incluidos ?? (email.articulos || []).length}/${email.articulos_totales ?? (email.articulos || []).length}</span>
    </button>`).join("");

  if (!selectedEmailId) selectedEmailId = emailDrafts[0].id;
  renderEmailComposer(selectedEmailId);
}

function renderEmailComposer(emailId) {
  const email = emailDrafts.find((row) => row.id === emailId);
  if (!email) return;
  currentEmail = email;
  selectedEmailId = email.id;
  const providerRequest = providerRequests.find((row) => row.id === email.solicitud_proveedor_id);
  currentProviderRequest = providerRequest || null;

  $("emailComposerPanel").innerHTML = `
    <div class="mail-compose-header">
      <div>
        <span class="section-kicker">Correo para proveedor</span>
        <h2>${escapeHtml(email.proveedor || providerRequest?.proveedor || "Proveedor")}</h2>
      </div>
      ${statusBadge(email.estado)}
    </div>
    <div class="provider-coverage-banner ${String(email.cobertura || "PARCIAL").toLowerCase()}">
      <strong>${email.cobertura === "TOTAL" ? "Cobertura total" : "Cobertura parcial"} · ${email.articulos_incluidos}/${email.articulos_totales} artículos</strong>
      ${(email.articulos_no_incluidos || []).length ? `<small>No incluidos: ${(email.articulos_no_incluidos || []).map((item) => escapeHtml(item.producto || "Producto")).join(", ")}</small>` : ""}
    </div>
    <div class="mail-form">
      <label class="mail-field"><span>Para</span><input id="emailToInput" type="email" value="${escapeHtml(email.destinatario)}"></label>
      <label class="mail-field"><span>Asunto</span><input id="emailSubjectInput" value="${escapeHtml(email.asunto)}"></label>
      <label class="mail-body-field"><span>Mensaje</span><textarea id="emailBodyInput" rows="15">${escapeHtml(email.contenido)}</textarea></label>
    </div>
    <div class="mail-reference">
      <span>Artículos incluidos</span>
      <div>${(email.articulos || []).map((item) => `<em>${escapeHtml(item.cantidad)} × ${escapeHtml(item.producto)}</em>`).join("")}</div>
    </div>
    <div class="mail-compose-actions">
      <button class="primary-action" type="button" onclick="saveCurrentEmail()">Guardar cambios</button>
    </div>`;
}

window.openEmailComposer = (id) => {
  selectedEmailId = id;
  renderEmailDraftWorkspace();
};

async function persistCurrentEmail(showMessage = true) {
  if (!selectedEmailId) return null;
  const email = emailDrafts.find((row) => row.id === selectedEmailId);
  if (!email) return null;
  const toInput = $("emailToInput");
  const subjectInput = $("emailSubjectInput");
  const bodyInput = $("emailBodyInput");
  if (!toInput || !subjectInput || !bodyInput) return email;

  const destinatario = toInput.value.trim();
  const asunto = subjectInput.value.trim();
  const contenido = bodyInput.value.trim();
  if (!destinatario || !asunto || !contenido) {
    showToast("Destinatario, asunto y mensaje son obligatorios.", true);
    return null;
  }

  const updated = await api(`/api/correos/${email.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ destinatario, asunto, contenido }),
  });
  mergeEmailRecord(updated);
  renderEmailDraftWorkspace();
  renderApprovalList();
  if (showMessage) showToast("Borrador guardado.");
  return updated;
}
window.saveCurrentEmail = () => persistCurrentEmail(true).catch(handleError);

$("providersBtn").addEventListener("click", async () => {
  if (!currentRequest) return;
  const button = $("providersBtn");
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = "Preparando…";
  try {
    providerRequests = await api(`/api/solicitudes/${currentRequest.id}/proveedores`, { method: "POST" });
    if (!providerRequests.length) {
      showToast("No se encontraron proveedores compatibles.", true);
      return;
    }
    await prepareAllEmailDrafts(providerRequests);
    unlockEmailStep(2);
    setEmailStep(2);
    showToast(`${emailDrafts.length} correo(s) preparado(s).`);
  } catch (e) {
    handleError(e);
  } finally {
    button.disabled = currentRequest?.estado !== "COMPLETO";
    button.textContent = previous;
  }
});

$("goToApprovalBtn").addEventListener("click", async () => {
  try {
    await persistCurrentEmail(false);
    unlockEmailStep(3);
    renderApprovalList();
    setEmailStep(3);
  } catch (e) { handleError(e); }
});

function approvalCounts() {
  return emailDrafts.reduce((counts, email) => {
    const status = String(email.estado || "BORRADOR").toUpperCase();
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
}

function renderApprovalList() {
  const list = $("emailApprovalList");
  if (!list) return;
  const counts = approvalCounts();
  $("emailApprovalSummary").innerHTML = `
    <div><strong>${emailDrafts.length}</strong><span>Correos</span></div>
    <div><strong>${counts.AUTORIZADO || 0}</strong><span>Autorizados</span></div>
    <div><strong>${counts.RECHAZADO || 0}</strong><span>Rechazados</span></div>
    <div><strong>${counts.BORRADOR || 0}</strong><span>Pendientes</span></div>`;

  list.innerHTML = emailDrafts.map((email) => `
    <article class="approval-mail-card ${normalizeStatus(email.estado)}">
      <div class="approval-mail-main">
        <div class="approval-mail-title">
          <strong>${escapeHtml(email.proveedor || "Proveedor")}</strong>
          ${statusBadge(email.estado)}
        </div>
        <span>${escapeHtml(email.destinatario)}</span>
        <small>${escapeHtml(email.asunto)}</small>
      </div>
      <div class="approval-mail-actions">
        <button type="button" class="secondary-action" onclick="editEmailFromApproval(${email.id})">Editar</button>
        <button type="button" class="reject-action" onclick="decideEmail(${email.id}, false)">Rechazar</button>
        <button type="button" class="authorize-action" onclick="decideEmail(${email.id}, true)">Autorizar</button>
      </div>
    </article>`).join("");

  const decided = emailDrafts.length > 0 && emailDrafts.every((email) => ["AUTORIZADO", "RECHAZADO", "ENVIADO"].includes(String(email.estado).toUpperCase()));
  $("goToSendBtn").disabled = !decided;
  if (decided) unlockEmailStep(4);
}

window.editEmailFromApproval = (id) => {
  selectedEmailId = id;
  setEmailStep(2);
};

window.decideEmail = async (id, authorized) => {
  try {
    const action = authorized ? "autorizar" : "rechazar";
    const updated = await api(`/api/correos/${id}/${action}`, { method: "POST" });
    mergeEmailRecord(updated);
    renderApprovalList();
    showToast(authorized ? "Correo autorizado." : "Correo rechazado.");
  } catch (e) { handleError(e); }
};

$("goToSendBtn").addEventListener("click", () => {
  unlockEmailStep(4);
  renderSendList();
  setEmailStep(4);
});

function renderSendList() {
  const list = $("emailSendList");
  if (!list) return;
  const authorized = emailDrafts.filter((email) => ["AUTORIZADO", "ENVIADO", "ERROR"].includes(String(email.estado).toUpperCase()));
  const rejected = emailDrafts.filter((email) => String(email.estado).toUpperCase() === "RECHAZADO");
  const sentCount = emailDrafts.filter((email) => String(email.estado).toUpperCase() === "ENVIADO").length;

  $("emailSendSummary").innerHTML = `
    <div><strong>${authorized.length}</strong><span>Habilitados para envío</span></div>
    <div><strong>${sentCount}</strong><span>Enviados</span></div>
    <div><strong>${rejected.length}</strong><span>Rechazados</span></div>`;

  if (!authorized.length) {
    list.innerHTML = '<div class="empty-state compact-empty"><p>No hay correos autorizados para enviar.</p></div>';
    return;
  }

  list.innerHTML = authorized.map((email) => {
    const status = String(email.estado).toUpperCase();
    return `
      <article class="send-mail-card">
        <div>
          <div class="approval-mail-title"><strong>${escapeHtml(email.proveedor || "Proveedor")}</strong>${statusBadge(email.estado)}</div>
          <span>${escapeHtml(email.destinatario)}</span>
          <small>${escapeHtml(email.asunto)}</small>
        </div>
        <button type="button" class="primary-action" ${status === "ENVIADO" ? "disabled" : ""} onclick="sendAuthorizedEmail(${email.id})">
          ${status === "ENVIADO" ? "Enviado" : "Enviar correo"}
        </button>
      </article>`;
  }).join("");
}

window.sendAuthorizedEmail = async (id) => {
  const email = emailDrafts.find((row) => row.id === id);
  if (!email) return;
  if (!confirm(`¿Enviar el correo autorizado a ${email.destinatario}?`)) return;
  try {
    const updated = await api(`/api/correos/${id}/enviar`, { method: "POST" });
    mergeEmailRecord(updated);
    renderSendList();
    renderApprovalList();
    showToast("Correo enviado mediante SMTP.");
  } catch (e) { handleError(e); }
};

document.querySelectorAll("[data-email-back]").forEach((button) => {
  button.addEventListener("click", () => setEmailStep(Number(button.dataset.emailBack)));
});

document.querySelectorAll(".stepper-step[data-email-step]").forEach((button) => {
  button.addEventListener("click", () => setEmailStep(Number(button.dataset.emailStep)));
});

function productOptions(selected) {
  return `<option value="">Sin identificar</option>` + catalogProducts.map((p) => `
    <option value="${p.id}" ${String(p.id) === String(selected) ? "selected" : ""}>${escapeHtml(p.nombre)}</option>
  `).join("");
}

function quoteDetailRow(d, i) {
  return `<div class="quote-detail" data-index="${i}">
    <div class="grid quote-detail-grid">
      <label>Producto<select class="qd-product">${productOptions(d.producto_servicio_id)}</select></label>
      <label>Descripción<input class="qd-description" value="${escapeHtml(d.descripcion ?? "")}"></label>
      <label>Cantidad<input class="qd-quantity" type="number" step="0.01" value="${d.cantidad ?? ""}"></label>
      <label>Precio unitario<input class="qd-unit" type="number" step="0.01" value="${d.precio_unitario ?? ""}"></label>
      <label>Precio total<input class="qd-total" type="number" step="0.01" value="${d.precio_total ?? ""}"></label>
      <label>Características<input class="qd-features" value="${escapeHtml(d.caracteristicas ?? "")}"></label>
    </div>
  </div>`;
}

function renderQuote(q) {
  currentQuote = q;
  const details = q.detalles.length ? q.detalles : [{
    producto_servicio_id: "",
    descripcion: "",
    cantidad: "",
    precio_unitario: "",
    precio_total: "",
    caracteristicas: "",
  }];

  $("quoteReview").className = "result-stack";
  $("quoteReview").innerHTML = `
    <article class="item quote-review-item">
      <div class="row">
        <div>
          <span class="item-index">Proforma #${q.id}</span>
          <h3>${escapeHtml(q.archivo)}</h3>
        </div>
        ${statusBadge(q.estado)}
      </div>
      <p>${q.mensaje
        ? `<span class="warning">${escapeHtml(q.mensaje)}</span>`
        : "Revise los datos extraídos antes de validarlos."}</p>
      <label>Proveedor</label>
      <select id="quote-provider">
        <option value="">Sin identificar</option>
        ${catalogProviders.map((p) => `<option value="${p.id}" ${p.nombre === q.proveedor ? "selected" : ""}>${escapeHtml(p.nombre)}</option>`).join("")}
      </select>
      <div id="quote-details">${details.map((d, i) => quoteDetailRow(d, i)).join("")}</div>
      <div class="inline">
        <button type="button" class="secondary" onclick="addQuoteDetail()">Agregar detalle</button>
        <button type="button" onclick="validateQuote()">Validar proforma</button>
      </div>
    </article>`;
}

window.addQuoteDetail = () => {
  const wrapper = document.createElement("div");
  wrapper.innerHTML = quoteDetailRow({
    producto_servicio_id: "",
    descripcion: "",
    cantidad: "",
    precio_unitario: "",
    precio_total: "",
    caracteristicas: "",
  }, document.querySelectorAll(".quote-detail").length);
  $("quote-details").appendChild(wrapper.firstElementChild);
};

window.validateQuote = async () => {
  if (!currentQuote) return;
  const detalles = [...document.querySelectorAll(".quote-detail")].map((row) => ({
    producto_servicio_id: row.querySelector(".qd-product").value ? Number(row.querySelector(".qd-product").value) : null,
    descripcion: row.querySelector(".qd-description").value || "Detalle capturado manualmente",
    cantidad: row.querySelector(".qd-quantity").value || null,
    precio_unitario: row.querySelector(".qd-unit").value || null,
    precio_total: row.querySelector(".qd-total").value || null,
    caracteristicas: row.querySelector(".qd-features").value || null,
  }));

  try {
    const q = await api(`/api/proformas/${currentQuote.id}/validar`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        proveedor_id: $("quote-provider").value ? Number($("quote-provider").value) : null,
        detalles,
      }),
    });
    renderQuote(q);
    await loadQuoteHistory(currentRequest.id);
    await refreshComparison();
    showToast("Proforma validada y comparación actualizada.");
  } catch (e) { handleError(e); }
};

function renderQuoteHistory(rows) {
  quoteRecords = rows;
  const history = $("quoteHistory");
  if (!rows.length) {
    history.className = "quote-history empty-state compact-empty";
    history.innerHTML = "<p>Todavía no hay PDF asociados a esta solicitud.</p>";
    return;
  }
  history.className = "quote-history";
  history.innerHTML = rows.map((q) => `
    <button class="quote-history-row" type="button" onclick="openQuote(${q.id})">
      <span class="quote-file-mark">PDF</span>
      <span class="quote-history-copy">
        <strong>${escapeHtml(q.archivo)}</strong>
        <small>${escapeHtml(q.proveedor ?? "Proveedor por confirmar")} · Proforma #${q.id}</small>
      </span>
      ${statusBadge(q.estado)}
    </button>
  `).join("");
}

async function loadQuoteHistory(requestId) {
  if (!requestId) return;
  const rows = await api(`/api/solicitudes/${requestId}/proformas`);
  renderQuoteHistory(rows);
}

window.openQuote = async (id) => {
  let quote = quoteRecords.find((q) => q.id === id);
  if (!quote) quote = await api(`/api/proformas/${id}`);
  renderQuote(quote);
};

async function searchRequests() {
  const query = $("quoteSearchInput").value.trim();
  const button = $("quoteSearchBtn");
  const panel = $("quoteSearchResults");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "Buscando…";
  panel.className = "search-results result-stack";
  panel.innerHTML = skeletonRows(3);
  try {
    const rows = await api(`/api/solicitudes/buscar?q=${encodeURIComponent(query)}`);
    renderSearchResults(rows);
  } catch (e) {
    handleError(e);
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = "Buscar";
  }
}

function renderSearchResults(rows) {
  const panel = $("quoteSearchResults");
  if (!rows.length) {
    panel.className = "search-results empty-state compact-empty";
    panel.innerHTML = "<p>No se encontraron solicitudes con ese criterio.</p>";
    return;
  }
  panel.className = "search-results";
  panel.innerHTML = rows.map((row) => `
    <button class="search-result-row" type="button" onclick="selectQuoteRequest(${row.id})">
      <span class="search-result-id">#${row.id}</span>
      <span class="search-result-copy">
        <strong>${escapeHtml(row.texto_original)}</strong>
        <small>
          ${row.proveedores.length ? escapeHtml(row.proveedores.join(", ")) : "Sin solicitudes por proveedor"}
          ${row.correos.length ? ` · ${escapeHtml(row.correos.join(", "))}` : ""}
          ${row.creada_en ? ` · ${escapeHtml(formatDate(row.creada_en))}` : ""}
        </small>
      </span>
      <span class="search-result-meta">
        ${statusBadge(row.estado)}
        <small>${row.proformas} PDF</small>
      </span>
    </button>
  `).join("");
}

window.selectQuoteRequest = async (requestId) => {
  try {
    const req = await api(`/api/solicitudes/${requestId}`);
    renderRequest(req);
    await loadQuoteHistory(req.id);
    await refreshComparison();
    showScreen("quotes");
    showToast(`Solicitud #${req.id} seleccionada.`);
  } catch (e) { handleError(e); }
};

$("quoteSearchBtn").addEventListener("click", searchRequests);
$("quoteSearchInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    searchRequests();
  }
});

$("uploadPdfBtn").addEventListener("click", async () => {
  if (!currentRequest) {
    showToast("Seleccione primero una solicitud.", true);
    return;
  }
  const files = [...$("pdfFile").files];
  if (!files.length) {
    showToast("Seleccione al menos un PDF antes de procesarlo.", true);
    return;
  }

  const button = $("uploadPdfBtn");
  button.disabled = true;
  $("pdfUploadProgress").textContent = `Procesando 0 de ${files.length}…`;
  const processed = [];
  try {
    for (let index = 0; index < files.length; index += 1) {
      const form = new FormData();
      form.append("file", files[index]);
      if ($("providerSelect").value) form.append("proveedor_id", $("providerSelect").value);
      const quote = await api(`/api/solicitudes/${currentRequest.id}/proformas`, { method: "POST", body: form });
      processed.push(quote);
      $("pdfUploadProgress").textContent = `Procesando ${index + 1} de ${files.length}…`;
    }
    $("pdfFile").value = "";
    $("pdfFileLabel").textContent = "Seleccionar PDF";
    await loadQuoteHistory(currentRequest.id);
    renderQuote(processed[processed.length - 1]);
    $("pdfUploadProgress").textContent = `${processed.length} PDF procesado(s). Revise la extracción antes de validar.`;
    showToast(`${processed.length} PDF procesado(s).`);
  } catch (e) {
    handleError(e);
  } finally {
    button.disabled = false;
  }
});

async function refreshComparison() {
  if (!currentRequest) return;
  $("comparisonBody").innerHTML = '<tr class="skeleton-table" aria-hidden="true"><td colspan="6"></td></tr><tr class="skeleton-table" aria-hidden="true"><td colspan="6"></td></tr>';
  const rows = await api(`/api/solicitudes/${currentRequest.id}/comparacion`);
  $("comparisonBody").innerHTML = rows.map((r) => `
    <tr>
      <td data-label="Producto">${escapeHtml(r.producto)}</td>
      <td data-label="Proveedor">${escapeHtml(r.proveedor)}</td>
      <td data-label="Cantidad">${escapeHtml(r.cantidad ?? "")}</td>
      <td data-label="Precio unitario">${escapeHtml(r.precio_unitario ?? "")}</td>
      <td data-label="Precio total">${escapeHtml(r.precio_total ?? "")}</td>
      <td data-label="Características">${escapeHtml(r.caracteristicas ?? "")}</td>
    </tr>
  `).join("") || '<tr><td colspan="6" class="table-empty">No hay proformas validadas todavía.</td></tr>';
}

$("comparisonBtn").addEventListener("click", async () => {
  try {
    await refreshComparison();
    showToast("Comparación actualizada.");
  } catch (e) { handleError(e); }
});

async function refreshCatalog() {
  const summary = await api("/api/catalogo/resumen");
  $("catalogSummary").innerHTML = Object.entries(summary).map(([key, value]) => `
    <div class="metric"><strong>${value}</strong>${escapeHtml(key)}</div>
  `).join("");

  catalogProducts = await api("/api/catalogo?tipo=productos");
  catalogProviders = await api("/api/catalogo?tipo=proveedores");
  $("providerSelect").innerHTML = '<option value="">Proveedor: detectar/seleccionar</option>' + catalogProviders.map((p) => `
    <option value="${p.id}">${escapeHtml(p.nombre)}</option>
  `).join("");
}

$("importCatalogBtn").addEventListener("click", async () => {
  const file = $("catalogFile").files[0];
  if (!file) {
    showToast("Seleccione un archivo CSV o XLSX.", true);
    return;
  }
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api(`/api/catalogo/importar?tipo=${encodeURIComponent($("importType").value)}`, {
      method: "POST",
      body: form,
    });
    $("importResult").textContent = JSON.stringify(result, null, 2);
    await refreshCatalog();
    showToast("Catálogo importado.");
  } catch (e) { handleError(e); }
});

function resetWorkspace() {
  currentRequest = null;
  currentQuote = null;
  currentEmail = null;
  currentProviderRequest = null;
  providerRequests = [];
  emailDrafts = [];
  selectedEmailId = null;
  quoteRecords = [];
  validationCorrectionMode = null;
  lastValidationPromptKey = null;
  completionAnnouncedForRequest = null;
  setRequestStatus("Sin solicitud");
  $("providersBtn").disabled = true;
  $("goToProvidersBtn").disabled = true;
  $("uploadPdfBtn").disabled = true;
  $("comparisonBtn").disabled = true;
  $("pdfFile").value = "";
  $("pdfFileLabel").textContent = "Seleccionar PDF";
  $("pdfUploadProgress").textContent = "";
  setItemsContent('<div class="empty-icon" aria-hidden="true">⌁</div><p>Analice una solicitud para comenzar la validación.</p>', true);
  setProvidersContent("<p>Complete una solicitud para preparar correos.</p>", true);
  $("quoteReview").className = "result-stack empty-state compact-empty";
  $("quoteReview").innerHTML = "<p>Seleccione una proforma para revisarla.</p>";
  $("quoteHistory").className = "quote-history empty-state compact-empty";
  $("quoteHistory").innerHTML = "<p>No hay una solicitud seleccionada.</p>";
  $("comparisonBody").innerHTML = '<tr><td colspan="6" class="table-empty">No hay proformas validadas todavía.</td></tr>';
  $("quoteSearchResults").className = "search-results empty-state compact-empty";
  $("quoteSearchResults").innerHTML = "<p>Busque y seleccione una solicitud.</p>";
  $("quoteSearchInput").value = "";
  $("requestText").value = "";
  autoGrowTextarea($("requestText"));
  if (initialConversationHtml) $("conversation").innerHTML = initialConversationHtml;
  $("conversation").scrollTop = 0;
  updateChatComposerMode();
  resetEmailWorkflow(true);
  updateRequestContext();
  showScreen("request");
  setTimeout(() => $("requestText").focus(), 150);
}

$("newRequestBtn").addEventListener("click", resetWorkspace);

function setupNavigation() {
  document.querySelectorAll("[data-screen]").forEach((button) => {
    button.addEventListener("click", () => showScreen(button.dataset.screen));
  });
}

$("sidebarToggle").addEventListener("click", () => $("sidebar").classList.toggle("open"));
document.addEventListener("click", (event) => {
  if (window.innerWidth > 720) return;
  const sidebar = $("sidebar");
  const toggle = $("sidebarToggle");
  if (sidebar.classList.contains("open") && !sidebar.contains(event.target) && !toggle.contains(event.target)) {
    sidebar.classList.remove("open");
  }
});

function updateFileLabels() {
  $("pdfFile").addEventListener("change", () => {
    const files = [...$("pdfFile").files];
    const label = $("pdfFileLabel");
    if (!files.length) label.textContent = "Seleccionar PDF";
    else if (files.length === 1) label.textContent = files[0].name;
    else label.textContent = `${files.length} PDF seleccionados`;
  });

  $("catalogFile").addEventListener("change", () => {
    const file = $("catalogFile").files[0];
    const label = document.querySelector(".compact-file span");
    if (label) label.textContent = file ? file.name : "Elegir CSV/XLSX";
  });
}

(async () => {
  document.title = "PLN Proformas";
  initialConversationHtml = $("conversation")?.innerHTML || "";
  const requestInput = $("requestText");
  requestInput?.addEventListener("input", () => autoGrowTextarea(requestInput));
  autoGrowTextarea(requestInput);

  setupNavigation();
  updateFileLabels();
  $("logoutBtn")?.addEventListener("click", logout);

  try {
    await loadSessionUser();
  } catch (error) {
    return;
  }
  resetEmailWorkflow(true);
  updateRequestContext();

  try {
    await api("/health");
  } catch (error) {
    console.warn("API no disponible.", error);
  }

  try {
    await refreshCatalog();
  } catch (e) {
    console.warn("No fue posible cargar el resumen del catálogo.", e);
  }
})();
