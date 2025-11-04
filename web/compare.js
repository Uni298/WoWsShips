// compare.js
// Frontend: ローカル tiers/*.json と images/ を参照して比較表示する
// 簡易実装: 起動時にすべての tier json を読み込み、select に埋める
// 使い方: web/ をルートとして静的サーバを起動 (例: python -m http.server)

const TIERS_PATH = "/tiers"; // サーバルートに tiers/ が見えること
const IMAGES_PATH = "/images"; // images/ が見えること

let allShips = []; // {ship_id, name, tier, type, image, image_url}

async function loadAllTiers() {
  const promises = [];
  for (let t=1; t<=10; t++) {
    promises.push(fetch(`${TIERS_PATH}/tier_${t}.json`).then(r => {
      if (!r.ok) return [];
      return r.json();
    }).catch(()=>[]));
  }
  const results = await Promise.all(promises);
  allShips = results.flat();
  // normalize name (some entries may be missing)
  allShips = allShips.map(s=>{
    return {
      ship_id: s.ship_id,
      name: s.name || (`ID:${s.ship_id}`),
      tier: s.tier,
      type: s.type || "",
      image: s.image || null,
      image_url: s.image_url || null
    };
  }).sort((a,b)=> a.name.localeCompare(b.name, 'ja'));
}

function populateSelects(filter="", tier="all") {
  const selA = document.getElementById("selectA");
  const selB = document.getElementById("selectB");
  selA.innerHTML = "";
  selB.innerHTML = "";
  const list = allShips.filter(s=>{
    if (tier !== "all" && String(s.tier) !== String(tier)) return false;
    if (!filter) return true;
    return s.name.includes(filter);
  });
  for (const s of list) {
    const optA = document.createElement("option");
    optA.value = s.ship_id;
    optA.textContent = `${s.name} (T${s.tier} ${s.type||""})`;
    const optB = optA.cloneNode(true);
    selA.appendChild(optA);
    selB.appendChild(optB);
  }
}

function getShipById(id) {
  return allShips.find(s => String(s.ship_id) === String(id));
}

function renderCard(domId, ship) {
  const el = document.getElementById(domId);
  el.innerHTML = "";
  if (!ship) {
    el.innerHTML = `<p>選択されていません</p>`;
    return;
  }
  const imgUrl = ship.image ? `${IMAGES_PATH}/${ship.image}` : (ship.image_url || "");
  const imgTag = imgUrl ? `<img src="${imgUrl}" alt="${ship.name}">` : "";
  const html = `
    ${imgTag}
    <h3>${ship.name}</h3>
    <div class="meta">Tier ${ship.tier} ・ ${ship.type || ""} ・ ID:${ship.ship_id}</div>
    <div id="${domId}-raw" class="raw"></div>
  `;
  el.innerHTML = html;

  // try to fetch full ship detail JSON (from ships_cache.json possibly) to show stats
  fetch(`/ships_cache.json`).then(r=>{
    if (!r.ok) return null;
    return r.json();
  }).then(cache=>{
    if (!cache) return;
    // find ship data by ship_id key (cache keys are ship_id string)
    const sdata = cache[String(ship.ship_id)];
    if (!sdata) return;
    // render some stats (try common keys)
    const rawDiv = document.getElementById(`${domId}-raw`);
    const lines = [];
    const statsCandidates = [
      ["max_speed", "最大速力"],
      ["survivability", "耐久性"],
      ["hull_strength", "耐久値"],
      ["hp", "HP"],
      ["hit_points", "HP"],
      ["main_battery", "主砲"], // complex
      ["torpedoes", "魚雷"],
      ["aircraft", "航空機"],
      ["concealment", "隠蔽性"],
      ["dispersion", "命中精度"]
    ];
    // show tier and nation
    if (sdata.nation) lines.push(`<div>国家: ${sdata.nation}</div>`);
    // try to show numeric fields in sdata (iterate)
    const numericKeys = ["hp", "hit_points", "durability", "survivability", "max_speed"];
    numericKeys.forEach(k=>{
      if (sdata[k] !== undefined) {
        lines.push(`<div>${k}: <strong>${sdata[k]}</strong></div>`);
      }
    });
    // also try sdata.default_profile or modules for main battery/dps
    if (sdata.default_profile && typeof sdata.default_profile === "object") {
      const prof = sdata.default_profile;
      for (const k of ["main_battery", "torpedoes", "aircraft"]) {
        if (prof[k]) {
          lines.push(`<div>${k}: ${JSON.stringify(prof[k])}</div>`);
        }
      }
    }
    rawDiv.innerHTML = lines.join("");
  }).catch(()=>{});
}

function compareShips(idA, idB) {
  const shipA = getShipById(idA);
  const shipB = getShipById(idB);
  renderCard("cardA", shipA);
  renderCard("cardB", shipB);
  // diff area: attempt simple diff by loading ships_cache.json and comparing numeric top-level fields
  const diffEl = document.getElementById("diffArea");
  if (!shipA || !shipB) {
    diffEl.innerHTML = "<p>2隻を選んでください。</p>";
    return;
  }
  fetch(`/ships_cache.json`).then(r=>r.ok ? r.json() : null).then(cache=>{
    if (!cache) {
      diffEl.innerHTML = "<p>詳細データが見つかりません (ships_cache.json を web ルートで公開してください)</p>";
      return;
    }
    const a = cache[String(shipA.ship_id)] || {};
    const b = cache[String(shipB.ship_id)] || {};
    // collect numeric keys present in either a or b
    const keys = new Set();
    for (const k in a) if (typeof a[k] === "number") keys.add(k);
    for (const k in b) if (typeof b[k] === "number") keys.add(k);
    // display differences
    let html = `<h4>数値差分</h4>`;
    if (keys.size === 0) {
      html += "<p>比較できる数値データがありません。</p>";
    } else {
      for (const k of Array.from(keys)) {
        const va = a[k] || 0;
        const vb = b[k] || 0;
        const diff = va - vb;
        const cls = diff > 0 ? "delta-positive" : (diff < 0 ? "delta-negative" : "");
        html += `<div class="stat-row"><div class="stat-name">${k}</div><div class="stat-value">${va} <span class="${cls}">(${diff>=0?"+":""}${diff})</span></div></div>`;
      }
    }
    diffEl.innerHTML = html;
  }).catch(err=>{
    diffEl.innerHTML = `<p>比較中にエラー: ${err}</p>`;
  });
}

// イベントバインド
document.addEventListener("DOMContentLoaded", async ()=>{
  await loadAllTiers();
  // initial populate
  populateSelects();
  document.getElementById("tierSelect").addEventListener("change", e=>{
    const t = e.target.value;
    const fA = document.getElementById("searchA").value.trim();
    populateSelects(fA, t);
  });
  document.getElementById("searchA").addEventListener("input", e=>{
    const q = e.target.value.trim();
    const t = document.getElementById("tierSelect").value;
    populateSelects(q, t);
  });
  document.getElementById("searchB").addEventListener("input", e=>{
    const q = e.target.value.trim();
    const t = document.getElementById("tierSelect").value;
    populateSelects(q, t);
  });

  document.getElementById("selectA").addEventListener("change", e=>{
    const idA = e.target.value;
    const idB = document.getElementById("selectB").value;
    compareShips(idA, idB);
  });
  document.getElementById("selectB").addEventListener("change", e=>{
    const idB = e.target.value;
    const idA = document.getElementById("selectA").value;
    compareShips(idA, idB);
  });

  document.getElementById("swapBtn").addEventListener("click", ()=>{
    const selA = document.getElementById("selectA");
    const selB = document.getElementById("selectB");
    const tmpA = selA.value;
    selA.value = selB.value;
    selB.value = tmpA;
    compareShips(selA.value, selB.value);
  });

});

