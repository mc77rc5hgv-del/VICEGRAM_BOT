/*
 * Логика одностраничного приложения (SPA).
 * Переключение вкладок и экранов происходит без перезагрузки страницы.
 */

const state = {
  tab: 'theory',
  theorySectionId: null,
  theoryTopicId: null,
  atlasQuery: '',
  trainerCategory: 'all',
  trainerDeck: [],
  trainerIndex: 0,
  trainerFlipped: false
};

function findTopic(topicId) {
  return ALL_TOPICS.find(t => t.id === topicId);
}

function findSection(sectionId) {
  return THEORY_SECTIONS.find(s => s.id === sectionId);
}

/* ---------- Навигация по вкладкам ---------- */

function switchTab(tabId) {
  state.tab = tabId;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  document.querySelectorAll('.view').forEach(v => {
    v.classList.toggle('active', v.id === 'view-' + tabId);
  });
  window.scrollTo(0, 0);
}

/* ---------- Теория ---------- */

function renderTheory() {
  const root = document.getElementById('view-theory');

  if (state.theoryTopicId) {
    renderTopicDetail(root, state.theoryTopicId);
    return;
  }

  if (state.theorySectionId) {
    renderTopicList(root, state.theorySectionId);
    return;
  }

  let html = '<div class="subview-header"><span class="subview-title">Теория</span></div>';
  html += '<div class="footer-note" style="text-align:left;padding:0 2px 14px;">Разделы курса нормальной анатомии по И.В. Гайворонскому. Выберите раздел, затем тему.</div>';
  THEORY_SECTIONS.forEach(section => {
    html += `
      <div class="section-card" data-action="open-section" data-id="${section.id}">
        <div class="icon-badge">${section.icon}</div>
        <div class="meta">
          <div class="title">${section.title}</div>
          <div class="count">${section.topics.length} ${pluralizeTopics(section.topics.length)}</div>
        </div>
        <div class="chevron">›</div>
      </div>`;
  });
  root.innerHTML = html;
}

function pluralizeTopics(n) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'тема';
  if ([2,3,4].includes(mod10) && ![12,13,14].includes(mod100)) return 'темы';
  return 'тем';
}

function renderTopicList(root, sectionId) {
  const section = findSection(sectionId);
  let html = `
    <div class="subview-header">
      <button class="back-btn" data-action="back-to-sections">‹ Разделы</button>
    </div>
    <div class="topic-detail-head" style="padding-top:0;">
      <div class="ru">${section.icon}&nbsp; ${section.title}</div>
    </div>
    <div class="topic-card">`;
  section.topics.forEach(topic => {
    html += `
      <div class="topic-row" data-action="open-topic" data-id="${topic.id}">
        <div class="dot"></div>
        <div class="titles">
          <div class="ru">${topic.ru}</div>
          <div class="la">${topic.la}</div>
        </div>
        <div class="chevron">›</div>
      </div>`;
  });
  html += '</div>';
  root.innerHTML = html;
}

function renderTopicDetail(root, topicId) {
  const topic = findTopic(topicId);
  const html = `
    <div class="subview-header">
      <button class="back-btn" data-action="back-to-topics" data-id="${topic.sectionId}">‹ ${topic.sectionTitle}</button>
    </div>
    <div class="topic-detail-head">
      <div class="ru">${topic.ru}</div>
      <div class="la">${topic.la}</div>
    </div>

    <div class="info-card">
      <div class="info-head"><span class="num">1</span> Определение</div>
      <div class="info-body">${topic.definition}</div>
    </div>
    <div class="info-card">
      <div class="info-head"><span class="num">2</span> Классификация</div>
      <div class="info-body">${topic.classification}</div>
    </div>
    <div class="info-card">
      <div class="info-head"><span class="num">3</span> Строение</div>
      <div class="info-body">${topic.structure}</div>
    </div>
    <div class="info-card vessels">
      <div class="info-head"><span class="num">4</span> Кровоснабжение и иннервация</div>
      <div class="info-body">${topic.vessels}</div>
    </div>

    <button class="topic-atlas-link" data-action="open-atlas-for-topic" data-id="${topic.id}">
      Смотреть в Атласе (${topic.atlas.length})
    </button>
  `;
  root.innerHTML = html;
  root.scrollTop = 0;
}

/* ---------- Атлас ---------- */

function renderAtlas() {
  const root = document.getElementById('view-atlas');
  const query = state.atlasQuery.trim().toLowerCase();

  let html = `
    <div class="subview-header"><span class="subview-title">Атлас</span></div>
    <div class="search-bar">
      <span>🔍</span>
      <input id="atlas-search" type="text" placeholder="Поиск темы или структуры…" value="${escapeAttr(state.atlasQuery)}" />
    </div>`;

  let anyMatch = false;
  THEORY_SECTIONS.forEach(section => {
    const topics = section.topics.filter(t => {
      if (!query) return true;
      return (t.ru + ' ' + t.la).toLowerCase().includes(query) ||
        t.atlas.some(a => a.ru.toLowerCase().includes(query));
    });
    if (!topics.length) return;
    anyMatch = true;
    html += `<div class="atlas-section-title">${section.icon} ${section.title}</div>`;
    topics.forEach(topic => {
      topic.atlas.forEach((plate, idx) => {
        html += renderAtlasPlate(topic, plate, idx);
      });
    });
  });

  if (!anyMatch) {
    html += '<div class="empty-state">Ничего не найдено. Попробуйте другой запрос.</div>';
  }

  root.innerHTML = html;
  wireAtlasImages(root);

  const searchInput = document.getElementById('atlas-search');
  if (searchInput) {
    searchInput.addEventListener('input', e => {
      state.atlasQuery = e.target.value;
      const caret = e.target.selectionStart;
      renderAtlas();
      const newInput = document.getElementById('atlas-search');
      if (newInput) {
        newInput.focus();
        newInput.setSelectionRange(caret, caret);
      }
    });
  }
}

function escapeAttr(str) {
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/*
 * Реальные изображения (сканы атласа Неттера / схемы Гайворонского) кладутся
 * в img/atlas/ по схеме "<id темы>-<номер иллюстрации>.<jpg|jpeg|png|webp>",
 * например img/atlas/heart-1.jpg. Полный список ожидаемых имён — в README.
 * Пока файла нет, вместо него показывается стилизованный плейсхолдер;
 * как только файл появляется в папке, картинка подставляется автоматически.
 */
const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp'];

function atlasImageBase(topicId, idx) {
  return `img/atlas/${topicId}-${idx + 1}`;
}

function renderAtlasPlate(topic, plate, idx) {
  const base = atlasImageBase(topic.id, idx);
  return `
    <div class="atlas-plate" data-action="open-plate-modal" data-topic="${topic.id}" data-idx="${idx}">
      <img class="atlas-img" data-base="${base}" alt="${escapeAttr(plate.ru)}" loading="lazy" />
      <div class="image-placeholder">
        <div class="ph-icon">🖼️</div>
        <div class="ph-source">${plate.source}</div>
        <div class="ph-topic">${topic.ru}</div>
        <div class="ph-desc">Вставьте иллюстрацию: «${plate.ru}»</div>
      </div>
    </div>`;
}

function tryNextExtension(img, extIndex) {
  if (extIndex >= IMAGE_EXTENSIONS.length) return;
  img.onerror = () => tryNextExtension(img, extIndex + 1);
  img.onload = () => img.parentElement.classList.add('loaded');
  img.src = `${img.dataset.base}.${IMAGE_EXTENSIONS[extIndex]}`;
}

function wireAtlasImages(root) {
  root.querySelectorAll('.atlas-img:not([data-wired])').forEach(img => {
    img.setAttribute('data-wired', '1');
    tryNextExtension(img, 0);
  });
}

function openPlateModal(topicId, idx) {
  const topic = findTopic(topicId);
  const plate = topic.atlas[idx];
  const overlay = document.getElementById('modal-overlay');
  const modalBody = document.getElementById('modal-body');
  modalBody.innerHTML = `
    <div class="atlas-plate modal-plate">
      <img class="atlas-img" data-base="${atlasImageBase(topic.id, idx)}" alt="${escapeAttr(plate.ru)}" />
      <div class="image-placeholder">
        <div class="ph-icon">🖼️</div>
        <div class="ph-source">${plate.source}</div>
        <div class="ph-desc">Вставьте сюда иллюстрацию из ${plate.source === 'Неттер' ? 'атласа Ф. Неттера' : 'пособий И.В. Гайворонского'}:<br><b>«${plate.ru}»</b></div>
      </div>
    </div>
    <div class="ph-topic" style="font-size:17px;margin:10px 0 0;">${topic.ru} <span style="opacity:.6;font-weight:400;">(<i>${topic.la}</i>)</span></div>
  `;
  wireAtlasImages(modalBody);
  overlay.classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

function openAtlasForTopic(topicId) {
  switchTab('atlas');
  const topic = findTopic(topicId);
  state.atlasQuery = topic.ru;
  renderAtlas();
}

/* ---------- Тренажёр (флеш-карточки) ---------- */

function shuffleArray(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function buildDeck(shuffle) {
  const cat = state.trainerCategory;
  let deck = cat === 'all' ? FLASHCARDS : FLASHCARDS.filter(c => c.category === cat);
  if (shuffle) deck = shuffleArray(deck);
  state.trainerDeck = deck;
  state.trainerIndex = 0;
  state.trainerFlipped = false;
}

function renderTrainer() {
  const root = document.getElementById('view-trainer');

  let chips = '';
  FLASHCARD_CATEGORIES.forEach(c => {
    chips += `<button class="chip ${c.id === state.trainerCategory ? 'active' : ''}" data-action="select-category" data-id="${c.id}">${c.icon} ${c.title}</button>`;
  });

  if (!state.trainerDeck.length) buildDeck(false);

  const card = state.trainerDeck[state.trainerIndex];

  let cardHtml;
  if (!card) {
    cardHtml = '<div class="empty-state">В этой категории пока нет карточек.</div>';
  } else {
    cardHtml = `
      <div class="trainer-progress">Карточка ${state.trainerIndex + 1} из ${state.trainerDeck.length}</div>
      <div class="flip-card-wrap">
        <div class="flip-card ${state.trainerFlipped ? 'flipped' : ''}" id="flip-card" data-action="flip-card">
          <div class="flip-face front">
            <div class="tag">Русский</div>
            <div class="term">${card.ru}</div>
            <div class="hint">Нажмите, чтобы увидеть латынь</div>
          </div>
          <div class="flip-face back">
            <div class="tag">Latina</div>
            <div class="term">${card.la}</div>
            <div class="hint">Нажмите, чтобы вернуться</div>
          </div>
        </div>
      </div>
      <div class="trainer-controls">
        <button class="trainer-btn" data-action="prev-card">‹</button>
        <button class="trainer-btn shuffle" data-action="shuffle-deck">🔀 Перемешать</button>
        <button class="trainer-btn" data-action="next-card">›</button>
      </div>`;
  }

  root.innerHTML = `
    <div class="subview-header"><span class="subview-title">Тренажёр латыни</span></div>
    <div class="chip-row">${chips}</div>
    ${cardHtml}
  `;
}

function selectCategory(catId) {
  state.trainerCategory = catId;
  buildDeck(false);
  renderTrainer();
}

function flipCard() {
  state.trainerFlipped = !state.trainerFlipped;
  const el = document.getElementById('flip-card');
  if (el) el.classList.toggle('flipped', state.trainerFlipped);
}

function nextCard() {
  if (!state.trainerDeck.length) return;
  state.trainerIndex = (state.trainerIndex + 1) % state.trainerDeck.length;
  state.trainerFlipped = false;
  renderTrainer();
}

function prevCard() {
  if (!state.trainerDeck.length) return;
  state.trainerIndex = (state.trainerIndex - 1 + state.trainerDeck.length) % state.trainerDeck.length;
  state.trainerFlipped = false;
  renderTrainer();
}

function shuffleDeck() {
  buildDeck(true);
  renderTrainer();
}

/* ---------- Делегирование кликов ---------- */

document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target.id === 'modal-overlay') closeModal();
});

document.addEventListener('click', e => {
  const target = e.target.closest('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  const id = target.dataset.id;

  switch (action) {
    case 'open-section':
      state.theorySectionId = id;
      renderTheory();
      break;
    case 'back-to-sections':
      state.theorySectionId = null;
      state.theoryTopicId = null;
      renderTheory();
      break;
    case 'open-topic':
      state.theoryTopicId = id;
      renderTheory();
      break;
    case 'back-to-topics':
      state.theoryTopicId = null;
      state.theorySectionId = id;
      renderTheory();
      break;
    case 'open-atlas-for-topic':
      openAtlasForTopic(id);
      break;
    case 'open-plate-modal':
      openPlateModal(target.dataset.topic, Number(target.dataset.idx));
      break;
    case 'close-modal':
      closeModal();
      break;
    case 'select-category':
      selectCategory(id);
      break;
    case 'flip-card':
      flipCard();
      break;
    case 'next-card':
      nextCard();
      break;
    case 'prev-card':
      prevCard();
      break;
    case 'shuffle-deck':
      shuffleDeck();
      break;
  }
});

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

/* ---------- Инициализация ---------- */

renderTheory();
renderAtlas();
renderTrainer();
switchTab('theory');
