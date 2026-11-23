"use strict";

const view = document.querySelector("#view");
const routes = new Set(["discover", "content", "collaborative", "search", "ratings", "evaluation"]);
const state = {
  ready: false, status: null, tags: [], ratings: {}, savedGames: new Map(), games: new Map(),
  route: "discover", q: "", tag: "", offset: 0, total: 0, pageSize: 12,
  query: "", searchEngine: "auto", searchResult: null, lastQuery: "", searchBusy: false,
  requestId: 0, saving: new Set(), saveErrors: new Set(),
};
let filterTimer, toastTimer, recommendationTimer;

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin", cache: "no-store", ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new Error("Could not connect to the app. Check that the local server is running and try again.");
  }
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(typeof body.detail === "string" ? body.detail : "Please check your input and try again.");
    error.status = response.status;
    throw error;
  }
  return body;
}

function announce(message) {
  document.querySelector("#announcer").textContent = message;
}

function notify(message, error = false) {
  const toast = document.querySelector("#toast");
  clearTimeout(toastTimer);
  toast.setAttribute("role", error ? "alert" : "status");
  toast.textContent = message;
  toast.classList.toggle("is-error", error);
  toast.hidden = false;
  toastTimer = setTimeout(() => { toast.hidden = true; }, error ? 6500 : 2500);
}

function heading(title, description, showRatingLink = true) {
  const count = Object.keys(state.ratings).length;
  const ratingLink = showRatingLink
    ? `<a class="rating-link" href="#ratings">${count} ${count === 1 ? "game" : "games"} rated ↗</a>`
    : "";
  return `<div class="view-heading"><div><h1 tabindex="-1">${escapeHTML(title)}</h1><p>${escapeHTML(description)}</p></div>${ratingLink}</div>`;
}

function skeletons(count = 8) {
  return `<div class="game-grid" aria-hidden="true">${"<div class=\"skeleton\"></div>".repeat(count)}</div>`;
}

function errorHTML(message, retry = "retry-view") {
  return `<div class="error-state" role="alert"><h2>We couldn't load that.</h2><p>${escapeHTML(message)}</p><button class="button" data-action="${retry}">Try again</button></div>`;
}

function cardHTML(game, ranked = false) {
  state.games.set(game.app_id, game);
  const id = Number(game.app_id);
  const title = escapeHTML(game.title);
  const rating = state.ratings[id] || 0;
  const stars = [1, 2, 3, 4, 5].map(n => `
    <label class="star ${n <= rating ? "is-filled" : ""}">
      <input type="radio" name="rating-${id}" value="${n}" data-star="${id}"
        aria-label="${n} ${n === 1 ? "star" : "stars"} for ${title}" ${rating === n ? "checked" : ""}>
      <span aria-hidden="true">★</span>
    </label>`).join("");
  return `<article class="game-card" data-game="${id}" aria-labelledby="game-title-${id}">
    <div class="cover"><span class="cover-fallback" aria-hidden="true">${title}</span>
      <img src="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${id}/header.jpg" alt="" width="460" height="215" loading="lazy" referrerpolicy="no-referrer">
      ${ranked ? `<span class="rank" aria-label="Rank ${game.rank}">${game.rank}</span>` : ""}
    </div>
    <div class="card-body">
      <h3 id="game-title-${id}" class="card-title">${title}</h3>
      <div class="tag-list">${game.tags.slice(0, 3).map(tag => `<span>${escapeHTML(tag)}</span>`).join("")}</div>
      ${ranked ? `<p class="reason">${escapeHTML(game.reason)}</p>` : ""}
      <details class="game-description"><summary>About this game</summary><p>${escapeHTML(game.description)}</p></details>
      <div class="card-bottom">
        <div class="rating-row"><fieldset class="star-group" ${state.saving.has(id) ? "disabled" : ""}>
          <legend class="sr-only">Your rating for ${title}</legend>${stars}
        </fieldset><span class="rating-copy">${state.saving.has(id) ? "Saving…" : rating ? `${rating} / 5` : "Rate this game"}</span></div>
        <div class="card-actions"><a class="store-link" href="https://store.steampowered.com/app/${id}/" target="_blank" rel="noopener noreferrer">View on Steam ↗</a>
          <button class="clear-rating" data-action="clear-rating" data-id="${id}" aria-label="Clear your rating for ${title}" ${rating ? "" : "hidden"} ${state.saving.has(id) ? "disabled" : ""}>Clear rating</button>
        </div>
      </div>
    </div>
  </article>`;
}

function renderCards(container, games, ranked = false) {
  container.innerHTML = `<div class="game-grid">${games.map(g => cardHTML(g, ranked)).join("")}</div>`;
  // Failed remote covers keep the local title fallback visible.
  container.querySelectorAll("img").forEach(img => {
    img.addEventListener("error", () => { img.hidden = true; }, { once: true });
  });
}

function paintRating(id) {
  const rating = state.ratings[id] || 0;
  document.querySelectorAll(`[data-game="${id}"]`).forEach(card => {
    card.querySelector("fieldset").disabled = state.saving.has(id);
    card.querySelectorAll("[data-star]").forEach(input => {
      input.checked = Number(input.value) === rating;
      input.parentElement.classList.toggle("is-filled", Number(input.value) <= rating);
    });
    const text = card.querySelector(".rating-copy");
    text.textContent = state.saving.has(id) ? "Saving…" : state.saveErrors.has(id) ? "Not saved" : rating ? `${rating} / 5` : "Rate this game";
    const clear = card.querySelector(".clear-rating");
    clear.hidden = !rating;
    clear.disabled = state.saving.has(id);
  });
}

function updateProfileCount() {
  const count = Object.keys(state.ratings).length;
  document.querySelector("#rating-count").textContent = count;
  const link = view.querySelector(".rating-link");
  if (link) link.textContent = `${count} ${count === 1 ? "game" : "games"} rated ↗`;
}

async function saveRating(id, rating) {
  if (state.saving.has(id)) return;
  const focused = document.activeElement;
  const restoreRadio = focused?.matches("input[data-star]") && Number(focused.dataset.star) === id;
  const restoreClear = focused?.matches('[data-action="clear-rating"]');
  state.saving.add(id);
  state.saveErrors.delete(id);
  paintRating(id);
  try {
    if (rating === null) {
      await request(`/api/ratings/${id}`, { method: "DELETE" });
      delete state.ratings[id];
      state.savedGames.delete(id);
    } else {
      await request(`/api/ratings/${id}`, { method: "PUT", body: JSON.stringify({ rating }) });
      state.ratings[id] = rating;
      state.savedGames.set(id, state.games.get(id));
    }
    updateProfileCount();
    const name = state.games.get(id)?.title || "Game";
    notify(rating === null ? `Rating cleared for ${name}.` : `${name} rated ${rating} out of 5.`);
    if (state.route === "ratings") renderRatings();
    if (state.route === "content" || state.route === "collaborative") {
      clearTimeout(recommendationTimer);
      recommendationTimer = setTimeout(loadRecommendations, 200);
    }
  } catch (error) {
    state.saveErrors.add(id);
    notify(`Rating not saved. ${error.message}`, true);
  } finally {
    state.saving.delete(id);
    paintRating(id);
    if (restoreRadio && document.activeElement === document.body) {
      const target = focused.isConnected ? focused : view.querySelector(`input[data-star="${id}"][value="${rating}"]`);
      target?.focus({ preventScroll: true });
    }
    if (restoreClear && document.activeElement === document.body) {
      const target = view.querySelector(`[data-game="${id}"] .clear-rating:not([hidden])`)
        || view.querySelector(`[data-game="${id}"] input[data-star]`)
        || view.querySelector(".game-card input[data-star]")
        || view.querySelector(".empty-state .button") || view.querySelector("h1");
      target?.focus({ preventScroll: true });
    }
  }
}

function renderDiscover() {
  view.innerHTML = heading("Find your next game.", "Rate the games you know. We'll help you find something new.") + `
    <form id="catalog-form" class="toolbar" role="search" aria-label="Find a game to rate">
      <label class="field field-title">Find a game<input type="search" id="game-query" name="q" placeholder="Search by title" maxlength="120" value="${escapeHTML(state.q)}"></label>
      <label class="field field-tag">Filter by tag<select id="game-tag" name="tag"><option value="">All tags</option>${state.tags.map(t => `<option value="${escapeHTML(t.tag)}" ${state.tag === t.tag ? "selected" : ""}>${escapeHTML(t.tag)} (${t.count})</option>`).join("")}</select></label>
    </form>
    <div class="section-line"><h2>Explore the catalogue</h2><span id="catalog-count">Loading games…</span></div>
    <div id="game-results">${skeletons()}</div><div id="pagination"></div>`;
  view.querySelector("#catalog-form").addEventListener("submit", event => {
    event.preventDefault(); clearTimeout(filterTimer); state.offset = 0; loadCatalogue();
  });
  view.querySelector("#game-query").addEventListener("input", event => {
    state.q = event.target.value;
    state.offset = 0;
    clearTimeout(filterTimer);
    filterTimer = setTimeout(loadCatalogue, 220);
  });
  view.querySelector("#game-tag").addEventListener("change", event => {
    state.tag = event.target.value; state.offset = 0; loadCatalogue();
  });
  loadCatalogue();
}

async function loadCatalogue() {
  if (state.route !== "discover") return;
  const token = ++state.requestId;
  const container = view.querySelector("#game-results");
  const focusedAction = document.activeElement?.dataset.action;
  view.setAttribute("aria-busy", "true");
  const params = new URLSearchParams({ q: state.q, tag: state.tag, offset: state.offset, limit: state.pageSize });
  try {
    const result = await request(`/api/games?${params}`);
    if (token !== state.requestId) return;
    state.total = result.total;
    view.querySelector("#catalog-count").textContent = `${result.total} ${result.total === 1 ? "game" : "games"}`;
    if (result.items.length) renderCards(container, result.items);
    else container.innerHTML = `<div class="empty-state"><h2>No games match those filters.</h2><p>Try another title or explore all tags.</p><button class="button" data-action="clear-filters">Clear filters</button></div>`;
    const start = result.total ? state.offset + 1 : 0;
    const end = Math.min(state.offset + state.pageSize, result.total);
    view.querySelector("#pagination").innerHTML = result.total > state.pageSize ? `
      <div class="pagination"><span>Showing ${start}–${end} of ${result.total} games</span><div class="pager-buttons"><button class="button" data-action="previous" ${state.offset === 0 ? "disabled" : ""}>← Previous</button><button class="button" data-action="next" ${end >= result.total ? "disabled" : ""}>Next →</button></div></div>` : "";
    announce(`${result.total} ${result.total === 1 ? "game" : "games"} found. Showing ${result.items.length}.`);
    if (["previous", "next"].includes(focusedAction) && document.activeElement === document.body) {
      const target = view.querySelector(`#pagination [data-action="${focusedAction}"]:not(:disabled)`)
        || view.querySelector("#pagination button:not(:disabled)");
      target?.focus({ preventScroll: true });
    }
  } catch (error) {
    if (token !== state.requestId) return;
    container.innerHTML = errorHTML(error.message, "retry-catalogue");
  } finally {
    if (token === state.requestId) view.setAttribute("aria-busy", "false");
  }
}

function methodLabel(result) {
  return ({ content: "Tag similarity", collaborative: "Similar players", popularity: "Sample favorites", neural: "Semantic search", lexical: "Keyword search" })[result.method];
}

function renderRecommendationPage() {
  const content = state.route === "content";
  view.innerHTML = heading(content ? "Based on your taste" : "Players with your taste", content ? "Games that share the tags you enjoy, shaped by your ratings." : "Discover games liked by players with similar preferences.") + `<div id="recommendation-results">${skeletons()}</div>`;
  loadRecommendations();
}

async function loadRecommendations() {
  if (!new Set(["content", "collaborative"]).has(state.route)) return;
  const method = state.route;
  const token = ++state.requestId;
  view.setAttribute("aria-busy", "true");
  const container = view.querySelector("#recommendation-results");
  const focusedCard = document.activeElement?.closest(".game-card");
  const focusedIndex = [...container.querySelectorAll(".game-card")].indexOf(focusedCard);
  try {
    const result = await request(`/api/recommendations?method=${method}`);
    if (token !== state.requestId) return;
    const introduction = result.fallback ? `
      <div class="onboarding"><div><h2>${Object.keys(state.ratings).length ? "Shape your next recommendations" : "A few ratings go a long way"}</h2><p>${escapeHTML(result.message)} These favorites give you a place to start.</p></div><a class="button button-primary" href="#discover">Find games to rate</a></div>` : "";
    const note = !result.fallback && method === "collaborative" ? `<p class="method-note">Based on ${result.neighbor_count} ${state.status.data_mode === "demo" ? "synthetic demo profiles" : "similar players"}. Already rated games are excluded.</p>` : "";
    container.innerHTML = introduction + note + `<div class="section-line"><h2>${result.fallback ? "Sample favorites" : `Your top ${result.items.length} picks`}</h2><span class="method-badge">${escapeHTML(methodLabel(result))}</span></div><div id="ranked-games"></div>`;
    if (result.items.length) renderCards(container.querySelector("#ranked-games"), result.items, true);
    else container.querySelector("#ranked-games").innerHTML = `<div class="empty-state"><h2>You've reached the end of this catalogue.</h2><p>There are no eligible unrated games to show. You can revisit your ratings or try a description search.</p><a class="button" href="#search">Describe a game</a></div>`;
    announce(`${result.items.length} recommendations loaded using ${methodLabel(result)}.`);
    if (focusedIndex >= 0 && document.activeElement === document.body) {
      const cards = [...container.querySelectorAll(".game-card")];
      const target = cards[Math.min(focusedIndex, cards.length - 1)]?.querySelector("input[data-star]")
        || view.querySelector("h1");
      target?.focus({ preventScroll: true });
    }
  } catch (error) {
    if (token !== state.requestId) return;
    container.innerHTML = errorHTML(error.message);
  } finally {
    if (token === state.requestId) view.setAttribute("aria-busy", "false");
  }
}

function renderRatings() {
  view.setAttribute("aria-busy", "false");
  const games = [...state.savedGames.values()].sort((a, b) => a.title.localeCompare(b.title));
  view.innerHTML = heading("Your ratings", "Your library of likes, dislikes, and everything in between.") + `<div class="section-line"><h2>${games.length} ${games.length === 1 ? "game rated" : "games rated"}</h2><span>1 = disliked · 5 = loved</span></div><div id="saved-games"></div>`;
  if (games.length) renderCards(view.querySelector("#saved-games"), games);
  else view.querySelector("#saved-games").innerHTML = `<div class="empty-state"><h2>Start with a game you know.</h2><p>A favorite helps us learn what you enjoy. A low rating helps us learn what to avoid. Your ratings are saved as you go.</p><a class="button button-primary" href="#discover">Explore games</a></div>`;
  announce(`${games.length} saved ${games.length === 1 ? "rating" : "ratings"}.`);
}

function renderSearch() {
  view.setAttribute("aria-busy", "false");
  view.innerHTML = heading("What do you want to play?", "Describe the setting, mood, or mechanics. Find a game that fits.") + `
    <form id="description-form" class="search-form">
      <label for="description-query">Your ideal game</label>
      <textarea id="description-query" name="description" minlength="2" maxlength="500" required placeholder="A peaceful farming game where I can grow crops and make friends in a small town…">${escapeHTML(state.query)}</textarea>
      <div class="search-options"><label class="field">Search method<select id="search-engine"><option value="auto" ${state.searchEngine === "auto" ? "selected" : ""}>${state.status.neural_index_ready ? "Semantic search" : "Keyword search"} (automatic)</option><option value="neural" ${state.searchEngine === "neural" ? "selected" : ""}>Semantic search</option><option value="lexical" ${state.searchEngine === "lexical" ? "selected" : ""}>Keyword search</option></select></label><button id="search-submit" class="button button-primary" type="submit">Find games →</button></div>
      <p class="search-hint">${state.status.neural_index_ready ? "Semantic search understands meaning. Keyword search matches words." : "Keyword search is available. Semantic search needs its model set up first."} Ctrl+Enter to search.</p>
    </form>
    <div class="examples"><span>Try an idea</span><button class="example-prompt" data-prompt="A peaceful farming game where I grow crops and make friends">A quieter pace</button><button class="example-prompt" data-prompt="A cooperative survival game where we explore, craft equipment, and build a base">Survive with friends</button><button class="example-prompt" data-prompt="A fantasy role-playing adventure with a rich story and meaningful choices">Get lost in a story</button></div>
    <div id="search-results"></div>`;
  const form = view.querySelector("#description-form");
  form.addEventListener("submit", event => { event.preventDefault(); searchGames(); });
  const input = view.querySelector("#description-query");
  input.addEventListener("input", event => { state.query = event.target.value; });
  input.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault(); form.requestSubmit();
    }
  });
  view.querySelector("#search-engine").addEventListener("change", event => { state.searchEngine = event.target.value; });
  if (state.searchResult) showSearchResults();
}

function showSearchResults() {
  const result = state.searchResult;
  const container = view.querySelector("#search-results");
  container.innerHTML = `<div class="section-line"><h2>${result.items.length ? `${result.items.length} games to explore` : "Search results"}</h2><span class="method-badge">${escapeHTML(methodLabel(result))}</span></div><p class="method-note">Results for “${escapeHTML(state.lastQuery)}”${result.method === "lexical" ? " · Word matches from the keyword baseline." : ""}</p><div id="search-games"></div>`;
  if (result.items.length) renderCards(container.querySelector("#search-games"), result.items, true);
  else container.querySelector("#search-games").innerHTML = `<div class="empty-state"><h2>Try a different description.</h2><p>No matches found. Include a setting or a mechanic, such as space exploration, farming, or turn-based combat.</p></div>`;
}

async function searchGames() {
  if (state.route !== "search" || state.searchBusy) return;
  const query = view.querySelector("#description-query").value.trim();
  if (query.length < 2) { notify("Enter at least two non-space characters.", true); return; }
  state.query = query;
  const token = ++state.requestId;
  state.searchBusy = true;
  view.setAttribute("aria-busy", "true");
  const button = view.querySelector("#search-submit");
  const restoreSubmit = document.activeElement === button;
  button.disabled = true;
  button.textContent = "Finding games…";
  view.querySelector("#search-results").innerHTML = skeletons(4);
  announce("Searching for games.");
  try {
    const result = await request("/api/search", { method: "POST", body: JSON.stringify({ query, engine: state.searchEngine }) });
    if (token !== state.requestId) return;
    state.searchResult = result;
    state.lastQuery = query;
    showSearchResults();
    announce(`${result.items.length} matches found using ${methodLabel(result)}.`);
  } catch (error) {
    if (token !== state.requestId) return;
    const message = error.status === 503 ? "Semantic search isn't available right now. Select keyword search and try again." : error.message;
    view.querySelector("#search-results").innerHTML = errorHTML(message, "retry-search");
  } finally {
    if (token === state.requestId) {
      state.searchBusy = false;
      view.setAttribute("aria-busy", "false");
      button.disabled = false;
      button.textContent = "Find games →";
      if (restoreSubmit && document.activeElement === document.body) button.focus({ preventScroll: true });
    }
  }
}

function evaluationHTML(report) {
  const { k, evaluated_users: users, training_interactions: training, models, diagnostics } = report;
  const number = new Intl.NumberFormat();
  const percent = new Intl.NumberFormat(undefined, {
    style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  const methods = [
    ["popularity", "Popularity baseline"],
    ["content", "Content-based filtering"],
    ["collaborative", "Collaborative filtering"],
  ];
  const rows = methods.map(([method, label]) => {
    const metrics = models[method];
    const recall = metrics[`recall@${k}`];
    const hits = metrics.hits ?? Math.round(recall * users);
    return `<tr>
      <th scope="row">${label}</th>
      <td><strong>${percent.format(recall)}</strong><small>${number.format(hits)} of ${number.format(users)} hits</small></td>
      <td>${metrics[`ndcg@${k}`].toFixed(6)}</td>
      <td>${percent.format(metrics.catalog_coverage)}</td>
      <td>${number.format(metrics.fallback_count)}</td>
    </tr>`;
  }).join("");
  const recallContext = diagnostics ? `
    <section class="evaluation-section" aria-labelledby="recall-heading">
      <h2 id="recall-heading">Popularity and the hidden games</h2>
      <dl class="evaluation-facts evaluation-diagnostics">
        <div><dt>Median positive training reviews per hidden game</dt><dd>${number.format(diagnostics.median_target_positive_training_reviews)}</dd></div>
        <div><dt>Median positive training reviews at rank ${k}</dt><dd>${diagnostics.median_popularity_cutoff == null ? "—" : number.format(diagnostics.median_popularity_cutoff)}</dd></div>
        <div><dt>Test cases with zero positive training reviews for the hidden game</dt><dd>${number.format(diagnostics.targets_without_positive_training_reviews)} <small>of ${number.format(users)}</small></dd></div>
      </dl>
      <p class="evaluation-explanation">The popularity baseline ranks games by how many players recommended them in the training data. Rank ${k} is the last slot in its top-${k} list.</p>
    </section>` : "";
  const source = report.synthetic_data ? "Synthetic demo data" : "Kaggle sample";
  return `
    <dl class="evaluation-facts evaluation-sample">
      <div><dt>Players evaluated</dt><dd>${number.format(users)}</dd></div>
      <div><dt>Training interactions</dt><dd>${number.format(training)}</dd></div>
      <div><dt>Games in the catalogue</dt><dd>${number.format(state.status.game_count)}</dd></div>
    </dl>
    <section class="evaluation-section" aria-labelledby="model-comparison">
      <div class="section-line"><h2 id="model-comparison">Model comparison</h2><span>${source}</span></div>
      <p class="evaluation-scroll-hint">Scroll to see all metrics.</p>
      <div class="evaluation-table-wrap" role="region" aria-labelledby="model-comparison" tabindex="0">
        <table class="evaluation-table">
          <thead><tr><th scope="col">Method</th><th scope="col">Recall@${k}</th><th scope="col">NDCG@${k}</th><th scope="col">Coverage</th><th scope="col">Fallbacks</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
    ${recallContext}
    <details class="evaluation-method">
      <summary>How the scores are calculated</summary>
      <p>One liked game is held out for each eligible player. A hit requires that exact game to appear in the top ${k} recommendations.</p>
      <p>Players qualify with at least three ratings, including two positive ratings. ${number.format(report.ineligible_users)} players fell below those thresholds. The split uses seed ${number.format(report.seed)}.</p>
      <dl>
        <div><dt>Recall@${k}</dt><dd>Share of players whose hidden game appeared in the top ${k}.</dd></div>
        <div><dt>NDCG@${k}</dt><dd>Gives more credit when the hidden game appears higher in the list.</dd></div>
        <div><dt>Coverage</dt><dd>Share of catalogue games recommended at least once.</dd></div>
        <div><dt>Fallbacks</dt><dd>Lists using popularity. This count includes every list from the popularity baseline.</dd></div>
      </dl>
    </details>`;
}

async function renderEvaluation() {
  const token = ++state.requestId;
  view.innerHTML = heading("Evaluation", "How often each method recovered a game the player liked.", false)
    + `<div class="evaluation-report"><p class="initial-loading" role="status">Loading evaluation results…</p></div>`;
  const container = view.querySelector(".evaluation-report");
  view.setAttribute("aria-busy", "true");
  try {
    const report = await request("/api/evaluation");
    if (token !== state.requestId) return;
    container.innerHTML = evaluationHTML(report);
    announce("Evaluation results loaded.");
  } catch (error) {
    if (token === state.requestId) container.innerHTML = errorHTML(error.message);
  } finally {
    if (token === state.requestId) view.setAttribute("aria-busy", "false");
  }
}

function loadRoute(focus = false) {
  if (!state.ready) return;
  clearTimeout(filterTimer);
  clearTimeout(recommendationTimer);
  ++state.requestId;
  state.searchBusy = false;
  const route = location.hash.slice(1);
  state.route = routes.has(route) ? route : "discover";
  document.querySelectorAll("[data-route]").forEach(link => {
    if (link.dataset.route === state.route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (state.route === "discover") renderDiscover();
  else if (state.route === "ratings") renderRatings();
  else if (state.route === "search") renderSearch();
  else if (state.route === "evaluation") renderEvaluation();
  else renderRecommendationPage();
  if (focus) {
    window.scrollTo({ top: 0, behavior: "instant" });
    view.querySelector("h1")?.focus({ preventScroll: true });
  }
  document.title = `${view.querySelector("h1")?.textContent || "Discover"} · Nextplay`;
}

async function boot() {
  view.setAttribute("aria-busy", "true");
  try {
    const [status, tags, profile] = await Promise.all([request("/api/status"), request("/api/tags"), request("/api/profile")]);
    state.status = status;
    state.tags = tags;
    state.ratings = profile.ratings;
    state.savedGames = new Map(profile.items.map(g => [g.app_id, g]));
    profile.items.forEach(g => state.games.set(g.app_id, g));
    document.querySelector("#source-badge").textContent = status.data_mode === "demo" ? "Demo catalogue" : "Kaggle sample";
    document.querySelector("#neural-state").textContent = status.neural_index_ready ? "Semantic search ready" : "Keyword search ready";
    document.querySelector("#source-summary").textContent = status.data_mode === "demo" ? "Demo data · Peer ratings are synthetic. Real-data results come after import." : "Recommendations use an imported Steam review sample.";
    document.querySelector("#source-description").textContent = `${status.source_note} This catalogue contains ${status.game_count} games, ${status.peer_count} peer profiles, and ${status.interaction_count} interactions. Your own 1–5 ratings are saved separately.`;
    updateProfileCount();
    state.ready = true;
    loadRoute();
  } catch (error) {
    view.innerHTML = errorHTML(error.message, "retry-boot");
    view.setAttribute("aria-busy", "false");
  }
}

view.addEventListener("change", event => {
  const star = event.target.closest("[data-star]");
  if (star) saveRating(Number(star.dataset.star), Number(star.value));
});

view.addEventListener("click", event => {
  const prompt = event.target.closest("[data-prompt]");
  if (prompt) {
    state.query = prompt.dataset.prompt;
    view.querySelector("#description-query").value = state.query;
    view.querySelector("#description-form").requestSubmit();
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  if (action === "clear-rating") saveRating(Number(button.dataset.id), null);
  else if (action === "retry-boot") boot();
  else if (action === "retry-view") loadRoute();
  else if (action === "retry-catalogue") loadCatalogue();
  else if (action === "retry-search") searchGames();
  else if (action === "previous" || action === "next") {
    state.offset += action === "next" ? state.pageSize : -state.pageSize;
    loadCatalogue();
  } else if (action === "clear-filters") {
    state.q = ""; state.tag = ""; state.offset = 0;
    view.querySelector("#game-query").value = "";
    view.querySelector("#game-tag").value = "";
    loadCatalogue();
  }
});

window.addEventListener("hashchange", () => loadRoute(true));
document.querySelector(".skip-link").addEventListener("click", event => {
  event.preventDefault();
  document.querySelector("#main").focus();
});
boot();

