import React, { useDeferredValue, useEffect, useState, useTransition } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);

const statusClass = {
  ready: "status-pill ok",
  loading: "status-pill warn",
  error: "status-pill error",
};

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch (_) {
      const text = await response.text();
      detail = text || detail;
    }
    throw new Error(detail);
  }
  return response.json();
}

function extractSeasonLabel(flashscoreLink) {
  const match = flashscoreLink.match(/(\d{4}-\d{4})\/?$/);
  return match ? match[1] : "season";
}

function triggerCsvDownload(url) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.setAttribute("download", "");
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function App() {
  const [summary, setSummary] = useState({
    sports_count: 0,
    countries_count: 0,
    leagues_count: 0,
    seasons_count: 0,
  });
  const [sports, setSports] = useState([]);
  const [leagues, setLeagues] = useState([]);
  const [seasons, setSeasons] = useState([]);
  const [selectedSportId, setSelectedSportId] = useState(null);
  const [selectedLeagueId, setSelectedLeagueId] = useState(null);
  const [sportSearch, setSportSearch] = useState("");
  const [leagueSearch, setLeagueSearch] = useState("");
  const [seasonSearch, setSeasonSearch] = useState("");
  const [status, setStatus] = useState({ tone: "loading", text: "Booting..." });
  const [error, setError] = useState("");
  const [loadingSports, setLoadingSports] = useState(false);
  const [loadingLeagues, setLoadingLeagues] = useState(false);
  const [loadingSeasons, setLoadingSeasons] = useState(false);
  const [isPending, startTransition] = useTransition();

  const deferredSportSearch = useDeferredValue(sportSearch);
  const deferredLeagueSearch = useDeferredValue(leagueSearch);
  const deferredSeasonSearch = useDeferredValue(seasonSearch);
  const normalizedSportSearch = deferredSportSearch.trim().toLowerCase();
  const normalizedLeagueSearch = deferredLeagueSearch.trim().toLowerCase();
  const normalizedSeasonSearch = deferredSeasonSearch.trim().toLowerCase();

  const visibleSports = sports.filter((sport) => {
    if (!normalizedSportSearch) {
      return true;
    }
    return sport.name.toLowerCase().includes(normalizedSportSearch);
  });

  const visibleLeagues = leagues.filter((league) => {
    if (!normalizedLeagueSearch) {
      return true;
    }
    const haystack = `${league.name} ${league.country_name} ${league.slug}`.toLowerCase();
    return haystack.includes(normalizedLeagueSearch);
  });

  const visibleSeasons = seasons.filter((season) => {
    if (!normalizedSeasonSearch) {
      return true;
    }
    const haystack = `${season.winner || ""} ${season.season_years || ""} ${season.flashscore_link}`.toLowerCase();
    return haystack.includes(normalizedSeasonSearch);
  });

  const selectedSport = sports.find((sport) => sport.id === selectedSportId) || null;
  const selectedLeague = leagues.find((league) => league.id === selectedLeagueId) || null;
  const currentStep = selectedLeague ? 3 : selectedSport ? 2 : 1;
  const progressPercent = currentStep === 1 ? 33 : currentStep === 2 ? 66 : 100;

  useEffect(() => {
    async function boot() {
      try {
        setLoadingSports(true);
        setError("");
        setStatus({ tone: "loading", text: "Loading sports..." });
        const [summaryPayload, sportsPayload] = await Promise.all([
          fetchJson("/api/summary"),
          fetchJson("/api/sports"),
        ]);
        const sportsWithLeagues = sportsPayload.filter((sport) => Number(sport.league_count || 0) > 0);
        startTransition(() => {
          setSummary(summaryPayload);
          setSports(sportsWithLeagues);
          setSelectedSportId(null);
          setSelectedLeagueId(null);
          setLeagues([]);
          setSeasons([]);
        });
        if (sportsWithLeagues.length === 0) {
          setStatus({ tone: "ready", text: "No sports with leagues" });
        } else {
          setStatus({ tone: "ready", text: "Pick a sport" });
        }
      } catch (err) {
        setError(err.message);
        setStatus({ tone: "error", text: "Load failed" });
      } finally {
        setLoadingSports(false);
      }
    }

    boot();
  }, []);

  async function handleSelectSport(sportId) {
    try {
      setLoadingLeagues(true);
      setLoadingSeasons(false);
      setError("");
      setLeagueSearch("");
      setSeasonSearch("");
      setStatus({ tone: "loading", text: "Loading leagues..." });
      const leaguesPayload = await fetchJson(`/api/sports/${sportId}/leagues`);
      startTransition(() => {
        setSelectedSportId(sportId);
        setSelectedLeagueId(null);
        setLeagues(leaguesPayload);
        setSeasons([]);
      });
      setStatus({ tone: "ready", text: "Pick a league" });
    } catch (err) {
      setError(err.message);
      setStatus({ tone: "error", text: "Leagues failed" });
    } finally {
      setLoadingLeagues(false);
    }
  }

  async function handleSelectLeague(leagueId) {
    try {
      setLoadingSeasons(true);
      setError("");
      setSeasonSearch("");
      setStatus({ tone: "loading", text: "Loading seasons + generating CSV..." });
      const seasonsPayload = await fetchJson(`/api/leagues/${leagueId}/seasons?limit=1000`);
      startTransition(() => {
        setSelectedLeagueId(leagueId);
        setSeasons(seasonsPayload);
      });
      // League click downloads latest season detailed CSV automatically.
      triggerCsvDownload(`/api/leagues/${leagueId}/matches-detailed.csv`);
      setStatus({ tone: "ready", text: "Seasons loaded and detailed CSV download started" });
    } catch (err) {
      setError(err.message);
      setStatus({ tone: "error", text: "Seasons failed" });
    } finally {
      setLoadingSeasons(false);
    }
  }

  function clearSportSelection() {
    startTransition(() => {
      setSelectedSportId(null);
      setSelectedLeagueId(null);
      setLeagues([]);
      setSeasons([]);
      setLeagueSearch("");
      setSeasonSearch("");
    });
    setStatus({ tone: "ready", text: "Pick a sport" });
  }

  function clearLeagueSelection() {
    startTransition(() => {
      setSelectedLeagueId(null);
      setSeasons([]);
      setSeasonSearch("");
    });
    setStatus({ tone: "ready", text: "Pick a league" });
  }

  function clearAllSelections() {
    startTransition(() => {
      setSelectedSportId(null);
      setSelectedLeagueId(null);
      setLeagues([]);
      setSeasons([]);
      setSportSearch("");
      setLeagueSearch("");
      setSeasonSearch("");
    });
    setStatus({ tone: "ready", text: "Pick a sport" });
  }

  function pickRandomSport() {
    if (!sports.length) {
      return;
    }
    const randomSport = sports[Math.floor(Math.random() * sports.length)];
    handleSelectSport(randomSport.id);
  }

  function pickRandomLeague() {
    if (!leagues.length) {
      return;
    }
    const randomLeague = leagues[Math.floor(Math.random() * leagues.length)];
    handleSelectLeague(randomLeague.id);
  }

  return html`
    <main className="app-shell">
      <div className="ambient-bg" aria-hidden="true">
        <span className="orb orb-1"></span>
        <span className="orb orb-2"></span>
        <span className="orb orb-3"></span>
        <span className="mesh"></span>
      </div>

      <header className="panel hero-panel reveal-surface">
        <div className="hero-copy">
          <div className="eyebrow">SportVisionX Control Center</div>
          <h1 className="hero-title gradient-title">Sports -> Leagues -> Seasons</h1>
          <p className="hero-subtitle">
            Click through your database step by step with fast filtering.
          </p>
          <div className="hero-foot">
            <span className=${statusClass[status.tone] || "status-pill"}>${isPending ? "Rendering..." : status.text}</span>
            ${selectedSport ? html`<span className="trail-chip">Sport: ${selectedSport.name}</span>` : null}
            ${selectedLeague ? html`<span className="trail-chip">League: ${selectedLeague.name}</span>` : null}
          </div>
          <div className="progress-wrap">
            <div className="progress-track">
              <span className="progress-fill" style=${{ width: `${progressPercent}%` }}></span>
            </div>
            <div className="progress-nodes">
              <span className=${`progress-node ${currentStep >= 1 ? "active" : ""}`}>Sport</span>
              <span className=${`progress-node ${currentStep >= 2 ? "active" : ""}`}>League</span>
              <span className=${`progress-node ${currentStep >= 3 ? "active" : ""}`}>Season</span>
            </div>
          </div>
          <div className="hero-actions">
            <button type="button" className="hero-btn" onClick=${pickRandomSport}>Random Sport</button>
            <button type="button" className="hero-btn" onClick=${pickRandomLeague} disabled=${!selectedSport}>Random League</button>
            <button type="button" className="hero-btn ghost" onClick=${clearAllSelections}>Clear All</button>
          </div>
          ${error ? html`<div className="error-banner">${error}</div>` : null}
        </div>
        <section className="metric-grid">
          <article className="metric-card reveal-up" style=${{ animationDelay: "40ms" }}>
            <div className="metric-value">${summary.sports_count}</div>
            <div className="metric-label">Sports (raw)</div>
          </article>
          <article className="metric-card reveal-up" style=${{ animationDelay: "90ms" }}>
            <div className="metric-value">${sports.length}</div>
            <div className="metric-label">Sports with leagues</div>
          </article>
          <article className="metric-card reveal-up" style=${{ animationDelay: "140ms" }}>
            <div className="metric-value">${summary.leagues_count}</div>
            <div className="metric-label">Leagues</div>
          </article>
          <article className="metric-card reveal-up" style=${{ animationDelay: "190ms" }}>
            <div className="metric-value">${summary.seasons_count}</div>
            <div className="metric-label">Seasons</div>
          </article>
        </section>
      </header>

      <section className="wizard-grid">
        <article className="panel step-card reveal-surface" style=${{ animationDelay: "80ms" }}>
          <div className="step-head">
            <div className="step-index">1</div>
            <div>
              <div className="step-title">Select Sport</div>
              <div className="step-subtitle">Only sports that have leagues are shown</div>
            </div>
          </div>
          <div className="card-toolbar">
            <span className="count-pill">${visibleSports.length} results</span>
          </div>
          <input
            className="search-input"
            type="search"
            value=${sportSearch}
            onChange=${(event) => setSportSearch(event.target.value)}
            placeholder="Search sport..."
          />
          <div className="scroll-list">
            ${
              loadingSports
                ? html`
                    <div className="skeleton-wrap">
                      <span className="skeleton-line"></span>
                      <span className="skeleton-line"></span>
                      <span className="skeleton-line"></span>
                    </div>
                  `
                : visibleSports.length === 0
                  ? html`<div className="empty">No sports available.</div>`
                  : visibleSports.map(
                      (sport, idx) => html`
                        <button
                          key=${sport.id}
                          className=${`choice-btn reveal-up ${sport.id === selectedSportId ? "active" : ""}`}
                          style=${{ animationDelay: `${Math.min(idx * 28, 420)}ms` }}
                          type="button"
                          onClick=${() => handleSelectSport(sport.id)}
                        >
                          <div className="choice-title">${sport.name}</div>
                          <div className="choice-meta mono">leagues: ${sport.league_count} | seasons: ${sport.season_count}</div>
                        </button>
                      `
                    )
            }
          </div>
        </article>

        <article className="panel step-card reveal-surface" style=${{ animationDelay: "120ms" }}>
          <div className="step-head with-action">
            <div className="step-head-main">
              <div className="step-index">2</div>
              <div>
                <div className="step-title">Select League</div>
                <div className="step-subtitle">Choose from the selected sport</div>
              </div>
            </div>
            ${selectedSport ? html`<button type="button" className="ghost-btn" onClick=${clearSportSelection}>Clear Sport</button>` : null}
          </div>
          <div className="card-toolbar">
            <span className="count-pill">${visibleLeagues.length} results</span>
          </div>
          <input
            className="search-input"
            type="search"
            value=${leagueSearch}
            onChange=${(event) => setLeagueSearch(event.target.value)}
            placeholder="Search league, country, slug..."
            disabled=${!selectedSport}
          />
          <div className="scroll-list">
            ${
              !selectedSport
                ? html`<div className="empty">Select a sport first.</div>`
                : loadingLeagues
                  ? html`
                      <div className="skeleton-wrap">
                        <span className="skeleton-line"></span>
                        <span className="skeleton-line"></span>
                        <span className="skeleton-line"></span>
                      </div>
                    `
                  : visibleLeagues.length === 0
                    ? html`<div className="empty">No leagues found.</div>`
                    : visibleLeagues.map(
                        (league, idx) => html`
                          <button
                            key=${league.id}
                            className=${`choice-btn reveal-up ${league.id === selectedLeagueId ? "active" : ""}`}
                            style=${{ animationDelay: `${Math.min(idx * 24, 360)}ms` }}
                            type="button"
                            onClick=${() => handleSelectLeague(league.id)}
                          >
                            <div className="choice-title">${league.name}</div>
                            <div className="choice-meta">${league.country_name}</div>
                            <div className="choice-meta mono">slug: ${league.slug} | seasons: ${league.season_count}</div>
                            <a
                              className="inline-link"
                              href=${league.flashscore_link}
                              target="_blank"
                              rel="noreferrer"
                              onClick=${(event) => event.stopPropagation()}
                            >
                              open flashscore
                            </a>
                          </button>
                        `
                      )
            }
          </div>
        </article>

        <article className="panel step-card reveal-surface" style=${{ animationDelay: "160ms" }}>
          <div className="step-head with-action">
            <div className="step-head-main">
              <div className="step-index">3</div>
              <div>
                <div className="step-title">Browse Seasons</div>
                <div className="step-subtitle">Winner and Flashscore season links</div>
              </div>
            </div>
            ${selectedLeague ? html`<button type="button" className="ghost-btn" onClick=${clearLeagueSelection}>Clear League</button>` : null}
          </div>
          <div className="card-toolbar">
            <span className="count-pill">${visibleSeasons.length} results</span>
          </div>
          <input
            className="search-input"
            type="search"
            value=${seasonSearch}
            onChange=${(event) => setSeasonSearch(event.target.value)}
            placeholder="Search winner or season link..."
            disabled=${!selectedLeague}
          />
          <div className="scroll-list">
            ${
              !selectedLeague
                ? html`<div className="empty">Select a league first.</div>`
                : loadingSeasons
                  ? html`
                      <div className="skeleton-wrap">
                        <span className="skeleton-line"></span>
                        <span className="skeleton-line"></span>
                        <span className="skeleton-line"></span>
                        <span className="skeleton-line"></span>
                      </div>
                    `
                  : visibleSeasons.length === 0
                    ? html`<div className="empty">No seasons found.</div>`
                    : visibleSeasons.map(
                        (season, idx) => html`
                          <article
                            key=${season.id}
                            className="season-card reveal-up"
                            style=${{ animationDelay: `${Math.min(idx * 18, 300)}ms` }}
                          >
                            <div className="season-head">
                              <span className="mono">#${season.id} | ${season.season_years || extractSeasonLabel(season.flashscore_link)}</span>
                              <span className="winner-pill">${season.winner || "winner unknown"}</span>
                            </div>
                            <div className="season-actions">
                              <button
                                type="button"
                                className="season-download-btn"
                                onClick=${() => triggerCsvDownload(`/api/leagues/${selectedLeagueId}/matches-detailed.csv?season_id=${season.id}`)}
                              >
                                Download Detailed CSV
                              </button>
                            </div>
                            <a className="season-link mono" href=${season.flashscore_link} target="_blank" rel="noreferrer">
                              ${season.flashscore_link}
                            </a>
                          </article>
                        `
                      )
            }
          </div>
        </article>
      </section>
    </main>
  `;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
