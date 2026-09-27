// Five Sites results page. Reads data.json (built by build_site.py) and renders
// the risk-profile chooser and the top-5 cards. No network calls beyond data.json.

const $ = (id) => document.getElementById(id);

// Small DOM helper: h("div", {class: "x"}, child, "text", ...). Text is never parsed as HTML.
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SOURCE_LABELS = {
  gridmap: "grid operator",
  vendor: "vendor estimate",
  landreg: "land registry",
  notes: "field notes",
  average: "average of all sites",
};
const FIELD_LABELS = {
  headroom: "headroom", distance: "distance", owner_status: "owner status",
  sentiment: "sentiment", flood_zone: "flood zone", area: "area",
};

const pretty = (v) => (v === null || v === undefined ? null : String(v).replace(/_/g, " "));

function fact(label, value, note) {
  return h("div", {},
    h("dt", {}, label),
    h("dd", {}, value ?? h("span", { class: "muted" }, "averaged"), note ? h("span", { class: "muted" }, ` ${note}`) : null));
}

function signal(label, s) {
  if (!s || s.value === "unknown") {
    return h("div", {}, h("h3", {}, label), h("p", { class: "muted" }, "Not in the field notes (averaged)."));
  }
  return h("div", {},
    h("h3", {}, `${label}: ${pretty(s.value)}`),
    h("blockquote", { class: "quote" }, `“${s.quote}”`, h("span", { class: "when" }, `Field note, ${s.date}`)));
}

function card(c) {
  const d = c.details;
  const area = d.area_m2 !== null ? `${Math.round(d.area_m2).toLocaleString("en")} m²` : null;
  const areaFromNote = c.criteria.find((x) => x.code === "C6").source === "notes";

  const summary = h("summary", {},
    h("div", { class: "card-head" },
      h("span", { class: "rank" }, c.rank),
      h("div", { class: "card-title" },
        h("p", { class: "card-name" }, c.name),
        h("p", { class: "card-id" }, c.site_id)),
      h("div", { class: "score" },
        h("div", { class: "score-num" }, c.score.toFixed(1)),
        h("div", { class: "score-max" }, "/ 100"))),
    h("div", { class: "bar" }, h("span", { style: `width:${c.score}%` })),
    c.badges.length ? h("div", { class: "badges" }, c.badges.map((b) => h("span", { class: `badge ${b.level}` }, b.label))) : null,
    h("div", { class: "toggle" }));

  const body = h("div", { class: "card-body" },
    h("h3", {}, "Site"),
    h("dl", { class: "facts" },
      fact("Region", d.region),
      fact("Site type", d.site_type),
      fact("Parcel", d.parcel_id),
      fact("Owner type", d.owner_type ?? "—"),
      fact("Headroom", d.headroom),
      fact("Distance", d.distance_km !== null ? `${d.distance_km} km` : null),
      fact("Flood zone", d.flood_zone),
      fact("Area", area, areaFromNote ? "(field note)" : null)),
    signal("Landowner", d.owner_status),
    signal("Community", d.sentiment),
    h("h3", {}, "Score breakdown"),
    h("table", { class: "breakdown" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Criterion"), h("th", { class: "num" }, "Tier"),
        h("th", { class: "num" }, "Points"), h("th", {}, "Source"))),
      h("tbody", {}, c.criteria.map((x) => h("tr", { class: x.source === "average" ? "avg" : "" },
        h("td", {}, `${x.code} ${x.name}`),
        h("td", { class: "num" }, `${x.source === "average" ? x.tier.toFixed(1) : x.tier}/5`),
        h("td", { class: "num" }, `${x.points}/${x.weight}`),
        h("td", {}, SOURCE_LABELS[x.source] ?? x.source))))),
    c.averaged.length
      ? h("p", { class: "muted" }, `Averaged: ${c.averaged.map((f) => FIELD_LABELS[f] ?? f).join(", ")}`)
      : null,
    c.flags.length ? h("div", {}, h("h3", {}, "Flags"), h("ul", { class: "flags" }, c.flags.map((f) => h("li", {}, f)))) : null);

  return h("li", {}, h("details", { class: "card" }, summary, body));
}

function showChooser(data) {
  $("results").hidden = true;
  $("choose").hidden = false;
  $("profiles").replaceChildren(...data.profiles.map((p) => {
    const btn = h("button", { class: "profile", type: "button", "data-key": p.key },
      h("span", { class: "profile-level" }, `${p.level} risk`),
      h("span", { class: "profile-title" }, p.title),
      h("span", { class: "profile-desc" }, p.description),
      h("span", { class: "profile-risk" }, p.risk));
    btn.addEventListener("click", () => { location.hash = p.key; });
    return btn;
  }));
}

function showResults(p) {
  $("choose").hidden = true;
  $("results").hidden = false;
  $("results-title").textContent = `${p.title}: top ${p.top.length} sites`;
  $("results-sub").textContent = `${p.level} risk · ${p.ranked} of ${p.total} candidate sites qualified under this profile.`;
  $("cards").replaceChildren(...[...p.top].sort((a, b) => b.score - a.score).map(card));
  window.scrollTo(0, 0);
}

function route(data) {
  const p = data.profiles.find((x) => x.key === location.hash.slice(1));
  p ? showResults(p) : showChooser(data);
}

fetch("data.json")
  .then((r) => { if (!r.ok) throw new Error(`data.json: HTTP ${r.status}`); return r.json(); })
  .then((data) => {
    $("footer").textContent = `Data generated ${data.generated_at}. Scores use the sponsor rubric (0–100). Synthetic data.`;
    $("back").addEventListener("click", () => { location.hash = ""; });
    window.addEventListener("hashchange", () => route(data));
    route(data);
  })
  .catch((e) => {
    $("error").hidden = false;
    $("error").textContent = `Couldn't load results (${e.message}).`;
  });
