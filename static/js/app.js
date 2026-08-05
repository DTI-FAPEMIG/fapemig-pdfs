// ============================================================
// FAPEMIG PDFs — Lógica Principal do Frontend (Otimizado)
// ============================================================

const state = {
  files: [], // { id, name, pages, thumbnail }
  numbering: {
    enabled: false,
    position: 'bottom-center',
    format: 'n_of_total',
    startPage: 1,
    fontSize: 12,
    color: [0, 0, 0],
    margin: 30,
    facingPages: false
  },
  isUploading: false
};

// ============================================================
// Elementos do DOM
// ============================================================
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const pdfGrid = document.getElementById('pdfGrid');
const emptyState = document.getElementById('emptyState');
const fileInfo = document.getElementById('fileInfo');
const fileCountEl = document.getElementById('fileCount');
const totalPagesEl = document.getElementById('totalPages');
const mergeSection = document.getElementById('mergeSection');
const mergeButton = document.getElementById('mergeButton');
const toastContainer = document.getElementById('toastContainer');
const progressOverlay = document.getElementById('progressOverlay');

// Elementos de numeração
const numberingToggle = document.getElementById('numberingToggle');
const numberingOptions = document.getElementById('numberingOptions');
const posButtons = document.querySelectorAll('.page-preview button');
const numberFormat = document.getElementById('numberFormat');
const fontSizeInput = document.getElementById('fontSize');
const fontSizeValue = document.getElementById('fontSizeValue');
const colorButtons = document.querySelectorAll('.color-pills button');
const marginInput = document.getElementById('margin');
const marginValue = document.getElementById('marginValue');
const startPageInput = document.getElementById('startPage');
const facingPagesInput = document.getElementById('facingPages');

// ============================================================
// SortableJS
// ============================================================
let sortableInstance = null;

function initSortable() {
  if (typeof Sortable !== 'undefined') {
    if (sortableInstance) sortableInstance.destroy();
    sortableInstance = new Sortable(pdfGrid, {
      animation: 200,
      handle: '.drag-handle',
      ghostClass: 'sortable-ghost',
      dragClass: 'sortable-drag',
      easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
      onEnd: () => {
        const cardIds = Array.from(pdfGrid.children).map(card => card.dataset.id);
        const reordered = [];
        cardIds.forEach(id => {
          const file = state.files.find(f => f.id === id);
          if (file) reordered.push(file);
        });
        state.files = reordered;
        updateOrderBadges();
      }
    });
  }
}

// ============================================================
// Upload — Individual com progresso
// ============================================================
uploadZone.addEventListener('click', () => {
  if (!state.isUploading) fileInput.click();
});

uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  if (!state.isUploading) uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
  uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('dragover');
  if (state.isUploading) return;
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (files.length > 0) {
    uploadFilesSequentially(files);
  } else {
    showToast('Por favor, selecione apenas arquivos PDF.', 'error');
  }
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files.length && !state.isUploading) {
    uploadFilesSequentially(Array.from(e.target.files));
  }
  fileInput.value = '';
});

/**
 * Upload otimizado: envia um arquivo por vez para feedback imediato.
 * Cada arquivo aparece na tela assim que é processado.
 */
async function uploadFilesSequentially(fileList) {
  state.isUploading = true;
  uploadZone.classList.add('uploading');

  const totalFiles = fileList.length;
  let successCount = 0;
  let errorCount = 0;

  // Mostrar progresso no upload zone
  const h2 = uploadZone.querySelector('h2');
  const p = uploadZone.querySelector('p');
  const originalH2 = h2.textContent;
  const originalP = p.textContent;

  for (let i = 0; i < fileList.length; i++) {
    const file = fileList[i];

    // Atualizar texto de progresso
    h2.textContent = `Processando ${i + 1} de ${totalFiles}...`;
    p.textContent = truncateFilename(file.name, 40);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/upload-single', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Erro no upload');
      }

      const result = await response.json();

      state.files.push({
        id: result.id,
        name: result.name,
        pages: result.pages,
        thumbnail: result.thumbnail
      });

      // Renderizar card imediatamente (sem re-renderizar tudo)
      appendCard(state.files[state.files.length - 1], state.files.length - 1);
      updateFileInfo();
      successCount++;

    } catch (error) {
      console.error(`Erro ao enviar ${file.name}:`, error);
      errorCount++;
    }
  }

  // Restaurar upload zone
  h2.textContent = originalH2;
  p.textContent = originalP;
  uploadZone.classList.remove('uploading');
  state.isUploading = false;

  // Inicializar SortableJS se ainda não foi
  if (state.files.length > 0 && !sortableInstance) {
    initSortable();
  }

  // Feedback
  if (successCount > 0) {
    showToast(`${successCount} arquivo${successCount > 1 ? 's' : ''} adicionado${successCount > 1 ? 's' : ''} com sucesso!`, 'success');
  }
  if (errorCount > 0) {
    showToast(`${errorCount} arquivo${errorCount > 1 ? 's' : ''} falhou${errorCount > 1 ? 'aram' : ''}.`, 'error');
  }
}

// ============================================================
// Renderização — Otimizada (append incremental)
// ============================================================

/** Adiciona UM card sem re-renderizar todo o grid */
function appendCard(file, index) {
  // Mostrar grid e esconder empty state
  emptyState.style.display = 'none';
  pdfGrid.style.display = 'grid';
  mergeSection.style.display = 'block';

  const card = createCardElement(file, index);
  pdfGrid.appendChild(card);
}

/** Cria o elemento DOM de um card */
function createCardElement(file, index) {
  const card = document.createElement('div');
  card.className = 'pdf-card';
  card.dataset.id = file.id;

  const thumbnailHTML = file.thumbnail
    ? `<img src="${file.thumbnail}" alt="${file.name}" class="thumbnail-img" loading="lazy" />`
    : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
         <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
         <polyline points="14 2 14 8 20 8"></polyline>
       </svg>`;

  card.innerHTML = `
    <div class="card-header">
      <div class="order-badge">${index + 1}</div>
      <div class="card-actions">
        <button class="icon-btn drag-handle" title="Arrastar para reordenar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="3" y1="12" x2="21" y2="12"></line>
            <line x1="3" y1="6" x2="21" y2="6"></line>
            <line x1="3" y1="18" x2="21" y2="18"></line>
          </svg>
        </button>
        <button class="icon-btn remove" data-id="${file.id}" title="Remover">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
    </div>
    <div class="thumbnail-container">
      ${thumbnailHTML}
    </div>
    <div class="card-info">
      <span class="filename" title="${file.name}">${truncateFilename(file.name, 28)}</span>
      <span class="page-count">${file.pages} página${file.pages !== 1 ? 's' : ''}</span>
    </div>
  `;

  card.querySelector('.remove').addEventListener('click', () => removeFile(file.id));
  return card;
}

/** Re-renderiza todo o grid (usado após remoção) */
function renderGrid() {
  if (state.files.length === 0) {
    emptyState.style.display = 'block';
    pdfGrid.style.display = 'none';
    fileInfo.style.display = 'none';
    mergeSection.style.display = 'none';
    return;
  }

  emptyState.style.display = 'none';
  pdfGrid.style.display = 'grid';
  fileInfo.style.display = 'flex';
  mergeSection.style.display = 'block';

  pdfGrid.innerHTML = '';
  state.files.forEach((file, index) => {
    const card = createCardElement(file, index);
    pdfGrid.appendChild(card);
  });

  updateFileInfo();
  initSortable();
}

function updateFileInfo() {
  if (state.files.length === 0) {
    fileInfo.style.display = 'none';
    return;
  }
  fileInfo.style.display = 'flex';
  const totalPages = state.files.reduce((sum, f) => sum + f.pages, 0);
  fileCountEl.textContent = `${state.files.length} arquivo${state.files.length !== 1 ? 's' : ''}`;
  totalPagesEl.textContent = `${totalPages} página${totalPages !== 1 ? 's' : ''}`;
}

function updateOrderBadges() {
  const badges = pdfGrid.querySelectorAll('.order-badge');
  badges.forEach((badge, index) => {
    badge.textContent = index + 1;
  });
}

async function removeFile(id) {
  const card = document.querySelector(`.pdf-card[data-id="${id}"]`);
  if (card) {
    card.style.transform = 'scale(0.8)';
    card.style.opacity = '0';
    card.style.transition = 'all 0.3s ease';
  }

  try {
    await fetch(`/api/files/${id}`, { method: 'DELETE' });
  } catch (e) {
    console.warn('Erro ao remover arquivo do servidor:', e);
  }

  setTimeout(() => {
    state.files = state.files.filter(f => f.id !== id);
    renderGrid();
  }, 300);
}

// ============================================================
// Utilitários
// ============================================================
function truncateFilename(name, maxLen) {
  if (name.length <= maxLen) return name;
  const ext = name.split('.').pop();
  const nameOnly = name.substring(0, name.lastIndexOf('.'));
  const truncLen = maxLen - ext.length - 4;
  if (truncLen <= 0) return name.substring(0, maxLen - 3) + '...';
  return nameOnly.substring(0, truncLen) + '...' + ext;
}

function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const iconSVG = type === 'success'
    ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent-green)" stroke-width="2">
         <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
         <polyline points="22 4 12 14.01 9 11.01"></polyline>
       </svg>`
    : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent-red)" stroke-width="2">
         <circle cx="12" cy="12" r="10"></circle>
         <line x1="12" y1="8" x2="12" y2="12"></line>
         <line x1="12" y1="16" x2="12.01" y2="16"></line>
       </svg>`;

  toast.innerHTML = `${iconSVG}<span>${message}</span>`;
  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ============================================================
// Painel de Numeração
// ============================================================
const POSITION_MAP = {
  'top-left': 'top-left',
  'top-center': 'top-center',
  'top-right': 'top-right',
  'middle-left': 'middle-left',
  'middle-center': 'middle-center',
  'middle-right': 'middle-right',
  'bottom-left': 'bottom-left',
  'bottom-center': 'bottom-center',
  'bottom-right': 'bottom-right'
};

numberingToggle.addEventListener('change', (e) => {
  state.numbering.enabled = e.target.checked;
  if (e.target.checked) {
    numberingOptions.classList.add('active');
  } else {
    numberingOptions.classList.remove('active');
  }
});

posButtons.forEach(btn => {
  const pos = btn.dataset.position;
  if (pos === state.numbering.position) btn.classList.add('active');
  btn.addEventListener('click', () => {
    posButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.numbering.position = pos;
  });
});

numberFormat.addEventListener('change', (e) => state.numbering.format = e.target.value);

fontSizeInput.addEventListener('input', (e) => {
  fontSizeValue.textContent = e.target.value;
  state.numbering.fontSize = parseInt(e.target.value);
});

colorButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    colorButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.numbering.color = btn.dataset.color.split(',').map(Number);
  });
});

marginInput.addEventListener('input', (e) => {
  marginValue.textContent = e.target.value;
  state.numbering.margin = parseInt(e.target.value);
});

startPageInput.addEventListener('input', (e) => {
  state.numbering.startPage = parseInt(e.target.value) || 1;
});

facingPagesInput.addEventListener('change', (e) => {
  state.numbering.facingPages = e.target.checked;
});

// ============================================================
// Merge / Compilar PDFs
// ============================================================
mergeButton.addEventListener('click', async () => {
  if (state.files.length === 0) return;

  const textSpan = mergeButton.querySelector('.merge-text');
  const loader = mergeButton.querySelector('.merge-loader');

  textSpan.style.display = 'none';
  loader.style.display = 'block';
  mergeButton.disabled = true;
  progressOverlay.style.display = 'flex';

  const fill = progressOverlay.querySelector('.progress-fill');
  let progress = 0;

  const progressInterval = setInterval(() => {
    progress += Math.random() * 8;
    if (progress > 90) progress = 90;
    fill.style.width = `${progress}%`;
  }, 300);

  try {
    const payload = {
      files: state.files.map(f => f.id),
      numbering: {
        enabled: state.numbering.enabled,
        position: POSITION_MAP[state.numbering.position] || state.numbering.position,
        format: state.numbering.format,
        start_page: state.numbering.startPage,
        font_size: state.numbering.fontSize,
        color: state.numbering.color,
        margin: state.numbering.margin,
        facing_pages: state.numbering.facingPages
      }
    };

    const response = await fetch('/api/merge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || 'Erro ao compilar PDFs');
    }

    const blob = await response.blob();

    clearInterval(progressInterval);
    fill.style.width = '100%';

    await new Promise(r => setTimeout(r, 400));

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'FAPEMIG_PDFs_compilado.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast('PDFs compilados com sucesso! Download iniciado.', 'success');

  } catch (error) {
    clearInterval(progressInterval);
    console.error('Erro ao compilar:', error);
    showToast(`Erro ao compilar PDFs: ${error.message}`, 'error');
  } finally {
    progressOverlay.style.display = 'none';
    textSpan.style.display = 'inline-block';
    loader.style.display = 'none';
    mergeButton.disabled = false;
    fill.style.width = '0%';
  }
});

// ============================================================
// Inicialização
// ============================================================
renderGrid();
