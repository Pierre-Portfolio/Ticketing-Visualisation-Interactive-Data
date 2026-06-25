#!/usr/bin/env python3
"""Genere ticketing_graph.html a partir de nodes.csv et edges.csv.

Projet d'apprentissage des bases de donnees NoSQL orientees graphe :
les donnees de ticketing (tickets, messages, utilisateurs, clients, tags)
sont modelisees en noeuds/relations, puis visualisees avec vis.js via pyvis.

Le script applique directement les correctifs de l'audit :
  - tooltips en texte brut (pas d'injection HTML -> pas de XSS stocke)
  - <!DOCTYPE html>, lang="fr", <meta viewport> et <title>
  - physique coupee une fois le graphe stabilise (perf sur gros graphes)
  - menus de selection / filtrage actifs (mise en evidence du voisinage)

Usage :
    pip install -r requirements.txt
    python generate_graph.py
"""

import csv
import json
import os
import re
from pyvis.network import Network

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NODES_CSV = os.path.join(BASE_DIR, "nodes.csv")
EDGES_CSV = os.path.join(BASE_DIR, "edges.csv")
OUTPUT_HTML = os.path.join(BASE_DIR, "ticketing_graph.html")

TITLE = "Visualisation interactive — Données de ticketing"

# Nombre maximum de noeuds a rendre. None = tout le jeu de donnees (5000).
# Mettre une valeur (ex. 800) pour un graphe plus leger/lisible : on garde alors
# les N premiers noeuds et uniquement les aretes reliant deux noeuds conserves.
MAX_NODES = None

# Apparence par type de noeud : (couleur, taille)
TYPE_STYLE = {
    "ticket":  ("#e06c75", 12),
    "message": ("#61afef", 8),
    "user":    ("#98c379", 14),
    "client":  ("#e5c07b", 16),
    "tag":     ("#c678dd", 6),
}
DEFAULT_STYLE = ("#aaaaaa", 10)

# Options vis.js (barnesHut). La physique est coupee apres stabilisation
# par post-traitement (voir _postprocess).
# Mise en evidence du voisinage au clic (remplace le code "mort" de l'export
# pyvis, qui n'etait jamais cable a un evenement). Injecte au post-traitement.
HIGHLIGHT_JS = """
    <script type="text/javascript">
      // Met en evidence le noeud clique et son voisinage (2 degres), grise le reste.
      // Les ARETES sont grisees elles aussi : seules celles reliant deux noeuds
      // conserves restent visibles (correction du highlight qui ne touchait que
      // les noeuds, laissant les aretes en pleine couleur au-dessus du gris).
      var highlightActive = false;

      // BFS du voisinage jusqu'a une profondeur donnee. Helper partage par le
      // highlight ET l'export de sous-graphe (evite la duplication). keep =
      // tout le voisinage retenu ; focus = selectionne + 1er degre (pleine
      // couleur). Voisinage stocke dans des Set : pas de doublons, pas de
      // travail redondant en O(aretes^2) sur les hubs.
      function collectNeighbourhood(seed, depth) {
        var keep = new Set([seed]);
        var focus = new Set([seed]);
        var frontier = [seed];
        for (var d = 1; d <= depth; d++) {
          var next = [];
          for (var i = 0; i < frontier.length; i++) {
            var nb = network.getConnectedNodes(frontier[i]);
            for (var n = 0; n < nb.length; n++) {
              if (!keep.has(nb[n])) {
                keep.add(nb[n]);
                next.push(nb[n]);
                if (d === 1) { focus.add(nb[n]); }
              }
            }
          }
          frontier = next;
        }
        return { keep: keep, focus: focus };
      }

      function neighbourhoodHighlight(params) {
        var all = nodes.get({ returnType: "Object" });
        // Mises a jour ciblees : on ne pousse au DataSet que les noeuds/aretes
        // dont la couleur (ou le label) change reellement, au lieu de re-pousser
        // les 5000 elements a chaque clic -> beaucoup moins de re-rendus.
        var nodeUpdates = [];
        var edgeUpdates = [];
        var allEdgesObj = edges.get({ returnType: "Object" });
        if (params.nodes.length > 0) {
          highlightActive = true;
          var nbh = collectNeighbourhood(params.nodes[0], window.HL_DEPTH || 2);
          var keep = nbh.keep, focusSet = nbh.focus;
          for (var id in all) {
            if (!all.hasOwnProperty(id)) continue;
            var node = all[id];
            var desired = focusSet.has(id) ? nodeColors[id]
                        : keep.has(id) ? "rgba(160,160,160,0.55)"
                        : "rgba(120,120,120,0.25)";
            var up = null;
            if (node.color !== desired) { up = { id: id, color: desired }; }
            // (de)masquage du label, seulement si l'etat change.
            if (keep.has(id)) {
              if (node.hiddenLabel !== undefined) {
                up = up || { id: id };
                up.label = node.hiddenLabel; up.hiddenLabel = undefined;
              }
            } else if (node.hiddenLabel === undefined) {
              up = up || { id: id };
              up.hiddenLabel = node.label; up.label = undefined;
            }
            if (up) { nodeUpdates.push(up); }
          }
          // Aretes : visibles seulement si leurs deux extremites sont dans keep.
          for (var eid in allEdgesObj) {
            if (!allEdgesObj.hasOwnProperty(eid)) continue;
            var e = allEdgesObj[eid];
            var ec = (keep.has(e.from) && keep.has(e.to)) ? "#555555" : "rgba(80,80,80,0.12)";
            if (e.color !== ec) { edgeUpdates.push({ id: e.id, color: ec }); }
          }
        } else if (highlightActive) {
          for (var id2 in all) {
            if (!all.hasOwnProperty(id2)) continue;
            var node2 = all[id2];
            var up2 = null;
            if (node2.color !== nodeColors[id2]) { up2 = { id: id2, color: nodeColors[id2] }; }
            if (node2.hiddenLabel !== undefined) {
              up2 = up2 || { id: id2 };
              up2.label = node2.hiddenLabel; up2.hiddenLabel = undefined;
            }
            if (up2) { nodeUpdates.push(up2); }
          }
          for (var eid2 in allEdgesObj) {
            if (!allEdgesObj.hasOwnProperty(eid2)) continue;
            var e2 = allEdgesObj[eid2];
            if (e2.color !== "#555555") { edgeUpdates.push({ id: e2.id, color: "#555555" }); }
          }
          highlightActive = false;
        } else {
          return;  // rien de selectionne et aucun highlight actif : no-op
        }
        if (edgeUpdates.length) { edges.update(edgeUpdates); }
        if (nodeUpdates.length) { nodes.update(nodeUpdates); }
      }
    </script>
"""

# --- Panneau de fonctionnalites (features 1 a 9) ---------------------------
# Couleur par type, alignee sur TYPE_STYLE (injectee dans le JS via __PALETTE__).
# Palette de priorite pour la coloration par attribut (feature 6).
PRIORITY_PALETTE = {
    "low": "#98c379",
    "medium": "#e5c07b",
    "high": "#d19a66",
    "critical": "#e06c75",
}

FEATURE_CSS = """
    <style type="text/css">
      #cp, #details {
        position: fixed; top: 12px; z-index: 1000;
        background: rgba(20,23,31,0.94); color: #e6e6e6;
        border: 1px solid #2a2f3a; border-radius: 8px;
        font: 12px/1.45 system-ui, sans-serif;
        box-shadow: 0 4px 18px rgba(0,0,0,0.45);
      }
      #cp { left: 12px; width: 250px; max-height: calc(100vh - 24px);
            overflow-y: auto; padding: 10px 12px; }
      #details { right: 12px; width: 250px; padding: 10px 12px; display: none; }
      #cp h2, #details h2 { font-size: 12px; text-transform: uppercase;
        letter-spacing: .04em; color: #9aa4b2; margin: 0 0 6px; }
      #cp section { border-top: 1px solid #2a2f3a; padding: 9px 0; }
      #cp section:first-of-type { border-top: 0; padding-top: 0; }
      #cp label { display: block; cursor: pointer; }
      #cp .row { display: flex; gap: 6px; align-items: center; }
      #cp input[type=text], #cp input[type=date], #cp select {
        width: 100%; box-sizing: border-box; background: #0f1117;
        color: #e6e6e6; border: 1px solid #2a2f3a; border-radius: 5px;
        padding: 4px 6px; }
      #cp button, #details button {
        background: #2a3140; color: #e6e6e6; border: 1px solid #3a4250;
        border-radius: 5px; padding: 5px 8px; cursor: pointer; font-size: 12px; }
      #cp button:hover, #details button:hover { background: #38415a; }
      .swatch { display: inline-block; width: 10px; height: 10px;
        border-radius: 50%; margin-right: 6px; vertical-align: middle; }
      #cp .muted { color: #8b94a3; }
      #cpToggle { position: fixed; top: 12px; left: 12px; z-index: 1001;
        display: none; }
      #searchMsg { color: #e06c75; min-height: 14px; }
      #details .kv { margin: 2px 0; }
      #details .kv b { color: #9aa4b2; font-weight: 600; }
      #neighList { margin: 4px 0 0; padding-left: 16px; max-height: 150px;
        overflow-y: auto; }
      #neighList li { cursor: pointer; }
      #neighList li:hover { color: #61afef; }

      /* --- Theme clair (active par la classe .light sur <body>) --- */
      body.light { background: #f4f6f9; }
      body.light #mynetwork { background-color: #f4f6f9 !important;
        border-color: #c9ced8; }
      body.light #cp, body.light #details {
        background: rgba(255,255,255,0.97); color: #1c2230;
        border-color: #d6dbe3; box-shadow: 0 4px 18px rgba(0,0,0,0.12); }
      body.light #cp h2, body.light #details h2 { color: #5a6677; }
      body.light #cp section { border-top-color: #e2e6ec; }
      body.light #cp input[type=text], body.light #cp input[type=date],
      body.light #cp select {
        background: #fff; color: #1c2230; border-color: #cfd5de; }
      body.light #cp button, body.light #details button {
        background: #eef1f6; color: #1c2230; border-color: #cfd5de; }
      body.light #cp button:hover, body.light #details button:hover {
        background: #e2e7ef; }
      body.light #cp .muted { color: #6b7585; }
      body.light #details .kv b { color: #5a6677; }
      body.light #neighList li:hover { color: #2563c9; }
    </style>
"""

FEATURE_HTML = """
    <button id="cpToggle">☰ Panneau</button>
    <div id="cp">
      <div class="row" style="justify-content:space-between">
        <h2 style="margin:0">Exploration</h2>
        <div class="row" style="gap:4px">
          <button id="themeToggle" title="Basculer clair / sombre">🌙</button>
          <button id="cpHide" title="Masquer">×</button>
        </div>
      </div>

      <section>
        <h2>Recherche</h2>
        <div class="row">
          <input type="text" id="searchInput" placeholder="id ou libellé…">
          <button id="searchBtn">OK</button>
        </div>
        <div id="searchMsg"></div>
      </section>

      <section>
        <h2>Types de nœuds</h2>
        <div id="typeFilters"></div>
      </section>

      <section>
        <h2>Relations</h2>
        <div id="relFilters"></div>
      </section>

      <section>
        <h2>Période</h2>
        <label class="muted">Du <input type="date" id="dateFrom"></label>
        <label class="muted" style="margin-top:4px">Au <input type="date" id="dateTo"></label>
        <div class="muted" style="margin-top:4px">Filtre les nœuds datés (tickets, messages).</div>
      </section>

      <section>
        <h2>Coloration</h2>
        <label><input type="radio" name="colormode" value="type" checked> Par type</label>
        <label><input type="radio" name="colormode" value="priority"> Par priorité (tickets)</label>
      </section>

      <section>
        <h2>Voisinage au clic</h2>
        <label class="muted">Profondeur
          <select id="depthSel">
            <option value="1">1 degré</option>
            <option value="2" selected>2 degrés</option>
            <option value="3">3 degrés</option>
          </select>
        </label>
      </section>

      <section>
        <h2>Export</h2>
        <div class="row">
          <button id="exportPng">PNG</button>
          <button id="exportSub">Sous-graphe</button>
        </div>
        <div class="muted" style="margin-top:4px">Le sous-graphe exporte le voisinage sélectionné.</div>
      </section>

      <section>
        <h2>Légende</h2>
        <div id="legend"></div>
      </section>

      <section>
        <h2>Statistiques</h2>
        <div id="stats"></div>
      </section>
    </div>

    <div id="details">
      <div class="row" style="justify-content:space-between">
        <h2 style="margin:0">Détails</h2>
        <button id="detClose" title="Fermer">×</button>
      </div>
      <div id="detBody"></div>
    </div>
"""

FEATURE_JS = """
    <script type="text/javascript">
    (function () {
      var TYPE_PALETTE = __PALETTE__;
      var PRIORITY_PALETTE = __PRIORITY__;
      var DIM = "rgba(120,120,120,0.25)";
      window.HL_DEPTH = 2;

      function $(id) { return document.getElementById(id); }
      function isDate(s) { return /^\\d{4}-\\d{2}-\\d{2}$/.test(s || ""); }
      // Echappe une valeur avant insertion dans de l'innerHTML (contexte texte
      // ET attribut). _safe() cote Python ne neutralise que < et > pour empecher
      // la fermeture prematuree de la balise script a la generation ; ici on
      // protege en plus l'injection d'attribut (guillemets) et les entites (&).
      var ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;",
                      '"': "&quot;", "'": "&#39;" };
      function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
          return ESC_MAP[c];
        });
      }

      // Etat des filtres
      var activeTypes = {};
      var activeRels = {};
      var colorMode = "type";

      // --- Couleur de base d'un noeud selon le mode courant -----------------
      function baseColor(n) {
        if (colorMode === "priority" && n.group === "ticket"
            && PRIORITY_PALETTE[n.a3]) {
          return PRIORITY_PALETTE[n.a3];
        }
        return TYPE_PALETTE[n.group] || "#aaaaaa";
      }

      // Reconstruit nodeColors (utilise par le highlight) + applique au graphe.
      function applyColors() {
        var all = nodes.get();
        for (var i = 0; i < all.length; i++) {
          nodeColors[all[i].id] = baseColor(all[i]);
        }
        // Si un noeud est mis en evidence, on re-joue le highlight pour que les
        // nouvelles couleurs de base s'appliquent immediatement (sinon le
        // changement de mode de coloration restait invisible tant qu'on n'avait
        // pas deselectionne le noeud).
        if (highlightActive) {
          var sel = network.getSelectedNodes();
          if (sel.length) { neighbourhoodHighlight({ nodes: [sel[0]] }); return; }
        }
        var ups = [];
        for (var j = 0; j < all.length; j++) {
          ups.push({ id: all[j].id, color: nodeColors[all[j].id] });
        }
        if (ups.length) { nodes.update(ups); }
      }

      // --- Filtres types / relations / periode ------------------------------
      function applyFilters() {
        var df = $("dateFrom").value, dt = $("dateTo").value;
        var allNodesArr = nodes.get();
        var visibleNode = {};
        var nodeUps = [];
        for (var i = 0; i < allNodesArr.length; i++) {
          var n = allNodesArr[i];
          var ok = activeTypes[n.group] !== false;
          if (ok && isDate(n.a2)) {
            if (df && n.a2 < df) { ok = false; }
            if (dt && n.a2 > dt) { ok = false; }
          }
          visibleNode[n.id] = ok;
          nodeUps.push({ id: n.id, hidden: !ok });
        }
        nodes.update(nodeUps);
        var allEdgesArr = edges.get();
        var edgeUps = [];
        for (var j = 0; j < allEdgesArr.length; j++) {
          var e = allEdgesArr[j];
          var relOk = activeRels[e.relation] !== false;
          var show = relOk && visibleNode[e.from] && visibleNode[e.to];
          edgeUps.push({ id: e.id, hidden: !show });
        }
        edges.update(edgeUps);
      }

      // --- Recherche --------------------------------------------------------
      function doSearch() {
        var q = ($("searchInput").value || "").trim().toLowerCase();
        $("searchMsg").textContent = "";
        if (!q) { return; }
        // On ignore les noeuds masques par un filtre (type / periode) : les
        // selectionner centrerait la vue sur un noeud invisible.
        var all = nodes.get();
        var hit = null;
        for (var i = 0; i < all.length; i++) {
          if (all[i].hidden) { continue; }
          if (String(all[i].id).toLowerCase() === q) { hit = all[i]; break; }
        }
        if (!hit) {
          for (var k = 0; k < all.length; k++) {
            if (all[k].hidden) { continue; }
            var lbl = (all[k].hiddenLabel || all[k].label || "");
            if (String(lbl).toLowerCase().indexOf(q) !== -1) { hit = all[k]; break; }
          }
        }
        if (!hit) { $("searchMsg").textContent = "Aucun nœud trouvé."; return; }
        network.selectNodes([hit.id]);
        network.focus(hit.id, { scale: 1.1, animation: true });
        neighbourhoodHighlight({ nodes: [hit.id] });
        showDetails(hit.id);
      }

      // --- Panneau de details ----------------------------------------------
      function showDetails(id) {
        var n = nodes.get(id);
        if (!n) { return; }
        var deg = network.getConnectedNodes(id);
        var html = "";
        html += '<div class="kv"><b>' + esc(n.hiddenLabel || n.label || id) + '</b></div>';
        html += '<div class="kv"><b>id</b> : ' + esc(id) + '</div>';
        html += '<div class="kv"><b>type</b> : ' + esc(n.group || "") + '</div>';
        if (n.a1) { html += '<div class="kv"><b>attr. 1</b> : ' + esc(n.a1) + '</div>'; }
        if (n.a2) { html += '<div class="kv"><b>attr. 2</b> : ' + esc(n.a2) + '</div>'; }
        if (n.a3) { html += '<div class="kv"><b>attr. 3</b> : ' + esc(n.a3) + '</div>'; }
        html += '<div class="kv"><b>voisins</b> : ' + deg.length + '</div>';
        if (deg.length) {
          html += '<ul id="neighList">';
          for (var i = 0; i < Math.min(deg.length, 50); i++) {
            var nb = nodes.get(deg[i]);
            html += '<li data-id="' + esc(deg[i]) + '">'
                  + esc((nb && (nb.hiddenLabel || nb.label)) || deg[i]) + '</li>';
          }
          html += '</ul>';
        }
        $("detBody").innerHTML = html;
        $("details").style.display = "block";
        var items = $("detBody").querySelectorAll("#neighList li");
        for (var j = 0; j < items.length; j++) {
          items[j].addEventListener("click", function () {
            var nid = this.getAttribute("data-id");
            network.selectNodes([nid]);
            network.focus(nid, { scale: 1.1, animation: true });
            neighbourhoodHighlight({ nodes: [nid] });
            showDetails(nid);
          });
        }
      }

      // --- Export -----------------------------------------------------------
      function download(name, dataUrl) {
        var a = document.createElement("a");
        a.href = dataUrl; a.download = name; a.click();
      }
      function exportPng() {
        var cv = network.canvas && network.canvas.frame
               ? network.canvas.frame.canvas : null;
        if (!cv) { return; }
        download("ticketing_graph.png", cv.toDataURL("image/png"));
      }
      function exportSubgraph() {
        var sel = network.getSelectedNodes();
        if (!sel.length) {
          $("searchMsg").textContent = "Sélectionnez d'abord un nœud.";
          return;
        }
        // Reutilise le BFS du highlight (meme profondeur).
        var keep = collectNeighbourhood(sel[0], window.HL_DEPTH || 2).keep;
        var outNodes = [];
        nodes.get().forEach(function (nd) {
          if (keep.has(nd.id)) {
            outNodes.push({ id: nd.id, label: nd.hiddenLabel || nd.label,
              type: nd.group, a1: nd.a1, a2: nd.a2, a3: nd.a3 });
          }
        });
        var outEdges = [];
        edges.get().forEach(function (e) {
          if (keep.has(e.from) && keep.has(e.to)) {
            outEdges.push({ source: e.from, target: e.to, relation: e.relation });
          }
        });
        var blob = JSON.stringify({ nodes: outNodes, edges: outEdges }, null, 2);
        download("sous_graphe.json",
          "data:application/json;charset=utf-8," + encodeURIComponent(blob));
      }

      // --- Construction de l'UF a partir des donnees ------------------------
      function buildUI() {
        var allNodesArr = nodes.get();
        var allEdgesArr = edges.get();

        // Types presents + cases a cocher
        var typeCounts = {};
        var minDate = null, maxDate = null;
        for (var i = 0; i < allNodesArr.length; i++) {
          var n = allNodesArr[i];
          typeCounts[n.group] = (typeCounts[n.group] || 0) + 1;
          if (isDate(n.a2)) {
            if (!minDate || n.a2 < minDate) { minDate = n.a2; }
            if (!maxDate || n.a2 > maxDate) { maxDate = n.a2; }
          }
        }
        var tf = $("typeFilters");
        Object.keys(typeCounts).sort().forEach(function (t) {
          activeTypes[t] = true;
          var col = TYPE_PALETTE[t] || "#aaaaaa";
          var lab = document.createElement("label");
          lab.innerHTML = '<input type="checkbox" data-type="' + esc(t) + '" checked> '
            + '<span class="swatch" style="background:' + esc(col) + '"></span>'
            + esc(t) + ' <span class="muted">(' + typeCounts[t] + ')</span>';
          tf.appendChild(lab);
        });
        tf.addEventListener("change", function (ev) {
          var t = ev.target.getAttribute("data-type");
          if (t !== null) { activeTypes[t] = ev.target.checked; applyFilters(); }
        });

        // Relations presentes + cases a cocher
        var relCounts = {};
        for (var j = 0; j < allEdgesArr.length; j++) {
          var r = allEdgesArr[j].relation || "(?)";
          relCounts[r] = (relCounts[r] || 0) + 1;
        }
        var rf = $("relFilters");
        Object.keys(relCounts).sort().forEach(function (r) {
          activeRels[r] = true;
          var lab = document.createElement("label");
          lab.innerHTML = '<input type="checkbox" data-rel="' + esc(r) + '" checked> '
            + esc(r) + ' <span class="muted">(' + relCounts[r] + ')</span>';
          rf.appendChild(lab);
        });
        rf.addEventListener("change", function (ev) {
          var r = ev.target.getAttribute("data-rel");
          if (r !== null) { activeRels[r] = ev.target.checked; applyFilters(); }
        });

        // Periode
        if (minDate) { $("dateFrom").value = minDate; $("dateFrom").min = minDate; }
        if (maxDate) { $("dateTo").value = maxDate; $("dateTo").max = maxDate; }
        $("dateFrom").addEventListener("change", applyFilters);
        $("dateTo").addEventListener("change", applyFilters);

        // Legende
        var leg = $("legend");
        Object.keys(TYPE_PALETTE).forEach(function (t) {
          var d = document.createElement("div");
          d.innerHTML = '<span class="swatch" style="background:'
            + esc(TYPE_PALETTE[t]) + '"></span>' + esc(t);
          leg.appendChild(d);
        });

        // Statistiques : top hubs par degre
        var deg = {};
        for (var k = 0; k < allEdgesArr.length; k++) {
          deg[allEdgesArr[k].from] = (deg[allEdgesArr[k].from] || 0) + 1;
          deg[allEdgesArr[k].to] = (deg[allEdgesArr[k].to] || 0) + 1;
        }
        var hubs = Object.keys(deg).map(function (id) { return [id, deg[id]]; })
          .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 5);
        var s = '<div class="kv">' + allNodesArr.length + ' nœuds · '
              + allEdgesArr.length + ' arêtes</div>';
        s += '<div class="kv muted" style="margin-top:4px">Nœuds les plus connectés :</div>';
        hubs.forEach(function (h) {
          var nb = nodes.get(h[0]);
          s += '<div class="kv" data-hub="' + esc(h[0]) + '" style="cursor:pointer">• '
            + esc((nb && (nb.hiddenLabel || nb.label)) || h[0])
            + ' <span class="muted">(' + h[1] + ')</span></div>';
        });
        $("stats").innerHTML = s;
        var hubEls = $("stats").querySelectorAll("[data-hub]");
        for (var m = 0; m < hubEls.length; m++) {
          hubEls[m].addEventListener("click", function () {
            var id = this.getAttribute("data-hub");
            network.selectNodes([id]);
            network.focus(id, { scale: 1.1, animation: true });
            neighbourhoodHighlight({ nodes: [id] });
            showDetails(id);
          });
        }
      }

      // --- Theme clair / sombre --------------------------------------------
      // Bascule la classe .light sur <body> (le CSS gere les panneaux et le
      // fond), et ajuste la couleur de police des noeuds via vis pour garder
      // les libelles lisibles sur fond clair. Choix memorise (localStorage).
      var theme = "dark";
      function applyTheme(t) {
        theme = (t === "light") ? "light" : "dark";
        document.body.classList.toggle("light", theme === "light");
        var btn = $("themeToggle");
        if (btn) { btn.textContent = (theme === "light") ? "☀️" : "🌙"; }
        // Libelles : blancs sur sombre, sombres sur clair.
        if (typeof network !== "undefined" && network) {
          network.setOptions({ nodes: { font: { color:
            (theme === "light") ? "#1c2230" : "#ffffff" } } });
        }
        try { localStorage.setItem("tg_theme", theme); } catch (e) {}
      }
      function toggleTheme() {
        applyTheme(theme === "light" ? "dark" : "light");
      }

      // --- Cablage ----------------------------------------------------------
      function wire() {
        $("themeToggle").addEventListener("click", toggleTheme);
        $("searchBtn").addEventListener("click", doSearch);
        $("searchInput").addEventListener("keydown", function (e) {
          if (e.key === "Enter") { doSearch(); }
        });
        var radios = document.querySelectorAll('input[name="colormode"]');
        for (var i = 0; i < radios.length; i++) {
          radios[i].addEventListener("change", function () {
            colorMode = this.value; applyColors();
          });
        }
        $("depthSel").addEventListener("change", function () {
          window.HL_DEPTH = parseInt(this.value, 10) || 2;
          var sel = network.getSelectedNodes();
          if (sel.length) { neighbourhoodHighlight({ nodes: [sel[0]] }); }
        });
        $("exportPng").addEventListener("click", exportPng);
        $("exportSub").addEventListener("click", exportSubgraph);
        $("detClose").addEventListener("click", function () {
          $("details").style.display = "none";
        });
        $("cpHide").addEventListener("click", function () {
          $("cp").style.display = "none"; $("cpToggle").style.display = "block";
        });
        $("cpToggle").addEventListener("click", function () {
          $("cp").style.display = "block"; this.style.display = "none";
        });
        // Details au clic (complete le highlight deja cable)
        network.on("click", function (params) {
          if (params.nodes.length) { showDetails(params.nodes[0]); }
        });
      }

      function start() {
        if (typeof network === "undefined" || !network) {
          return setTimeout(start, 60);  // attend la creation du reseau
        }
        buildUI();
        wire();
        var saved = "dark";
        try { saved = localStorage.getItem("tg_theme") || "dark"; } catch (e) {}
        applyTheme(saved);
      }
      start();
    })();
    </script>
"""

OPTIONS = """
const options = {
  "physics": {
    "enabled": true,
    "barnesHut": {
      "gravitationalConstant": -8000,
      "centralGravity": 0.3,
      "springLength": 120,
      "springConstant": 0.04,
      "damping": 0.09,
      "avoidOverlap": 0.3
    },
    "maxVelocity": 50,
    "minVelocity": 0.75,
    "stabilization": {"iterations": 150}
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 100,
    "hideEdgesOnDrag": true,
    "navigationButtons": true,
    "keyboard": true
  },
  "edges": {
    "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
    "smooth": {"type": "continuous"},
    "color": {"color": "#555555", "highlight": "#ffffff"}
  },
  "nodes": {
    "font": {"size": 11, "color": "#ffffff"},
    "borderWidth": 1.5,
    "shadow": true
  }
}
"""


def _read_csv(path, required):
    """Lit un CSV en liste de dicts et valide la presence des colonnes attendues.

    Leve une erreur claire si le fichier est introuvable, vide, ou s'il manque
    une colonne (au lieu d'un KeyError opaque au moment du add_node/add_edge).
    """
    if not os.path.exists(path):
        raise FileNotFoundError("Fichier introuvable : {}".format(path))
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV vide ou sans en-tete : {}".format(path))
        missing = [c for c in required if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                "Colonnes manquantes dans {} : {} (trouvees : {})".format(
                    path, ", ".join(missing), ", ".join(reader.fieldnames)
                )
            )
        return list(reader)


def _safe(text):
    """Neutralise les chevrons < > dans le texte issu des CSV.

    pyvis embarque labels et tooltips en JSON a l'interieur d'un bloc <script>.
    json.dumps echappe les guillemets mais PAS le caractere '<' : une valeur
    contenant '</script>' fermerait la balise et permettrait une injection
    HTML/JS si les CSV ne sont pas de confiance. vis.js affiche ces champs en
    texte brut (canvas), donc remplacer < et > par des chevrons unicode (‹ ›)
    preserve la lisibilite tout en empechant toute fermeture de balise.
    """
    return str(text).replace("<", "‹").replace(">", "›")


def _node_tooltip(row):
    """Construit un tooltip en TEXTE BRUT (aucune balise -> aucun risque XSS)."""
    lines = [
        row.get("label") or row.get("id", ""),
        "Type : {}".format(row.get("type", "")),
        "Attribut 1 : {}".format(row.get("attribute1", "")),
        "Attribut 2 : {}".format(row.get("attribute2", "")),
        "Attribut 3 : {}".format(row.get("attribute3", "")),
    ]
    return _safe("\n".join(lines))


def build_network():
    # font_color n'est PAS passe ici : il forcerait un objet "font" duplique
    # sur chacun des 5000 noeuds. La police est definie une seule fois dans
    # OPTIONS (nodes.font), ce qui allege fortement le HTML genere.
    net = Network(
        height="850px",
        width="100%",
        bgcolor="#0f1117",
        directed=True,
    )

    node_rows = _read_csv(NODES_CSV, required=("id",))
    if MAX_NODES is not None:
        node_rows = node_rows[:MAX_NODES]

    node_ids = set()
    for row in node_rows:
        node_id = _safe((row.get("id") or "").strip())
        if not node_id:
            continue  # ligne sans identifiant : ignoree au lieu de planter
        color, size = TYPE_STYLE.get(row.get("type"), DEFAULT_STYLE)
        # a1/a2/a3 sont embarques (en plus du tooltip) pour donner aux features
        # un acces structure aux attributs : coloration par attribut, filtre
        # temporel sur la date, panneau de details.
        net.add_node(
            node_id,
            label=_safe(row.get("label") or node_id),
            title=_node_tooltip(row),
            color=color,
            size=size,
            shape="dot",
            group=row.get("type", "autre"),
            a1=_safe(row.get("attribute1", "")),
            a2=_safe(row.get("attribute2", "")),
            a3=_safe(row.get("attribute3", "")),
        )
        node_ids.add(node_id)

    edge_index = 0
    for row in _read_csv(EDGES_CSV, required=("source", "target")):
        src = _safe((row.get("source") or "").strip())
        dst = _safe((row.get("target") or "").strip())
        if not src or not dst or src not in node_ids or dst not in node_ids:
            continue  # arete orpheline ou incomplete : ignoree
        try:
            weight = float(row.get("weight", 1) or 1)
        except ValueError:
            weight = 1.0
        relation = _safe(row.get("relation", ""))
        # id explicite + relation embarquee : indispensables pour filtrer les
        # aretes par type de relation cote client.
        net.add_edge(
            src, dst,
            id="e{}".format(edge_index),
            title="{} (poids : {:g})".format(relation, weight),
            value=weight,
            relation=relation,
        )
        edge_index += 1

    net.set_options(OPTIONS)
    return net


def _require(html, anchor, what):
    """Verifie qu'une ancre attendue du template pyvis est presente.

    Sans cela, une montee de version de pyvis qui renomme/supprime l'ancre
    produirait silencieusement un HTML incomplet (physique jamais coupee,
    highlight jamais cable...). On prefere une erreur explicite.
    """
    if anchor not in html:
        raise RuntimeError(
            "Ancre introuvable dans le HTML pyvis ({}). Le template a peut-etre "
            "change de version : adapter _postprocess(). Ancre attendue : {!r}".format(
                what, anchor
            )
        )


def _postprocess(html):
    """Applique les correctifs qui ne sont pas exposes par l'API pyvis."""
    # 0) retire la reference morte a lib/bindings/utils.js : pyvis l'emet
    #    systematiquement mais le fichier n'est pas embarque ici (404 en
    #    console, notamment sur la demo GitHub Pages). Le panneau custom
    #    n'en depend pas.
    html = html.replace(
        '<script src="lib/bindings/utils.js"></script>', "", 1
    )
    # 1) DOCTYPE + lang
    if not html.lstrip().startswith("<!DOCTYPE"):
        html = html.replace("<html>", '<!DOCTYPE html>\n<html lang="fr">', 1)
    # 2) viewport + title + CSP dans le <head>
    #    La CSP est une defense en profondeur : tout etant inline dans la sortie
    #    pyvis, 'unsafe-inline' reste necessaire (la protection XSS reelle vient
    #    de esc()/_safe), mais elle verrouille default-src a 'none', limite les
    #    origines externes au seul CDN utilise (vis-network) et bloque
    #    base-uri / form-action / object-src.
    _require(html, '<meta charset="utf-8">', "meta charset")
    csp = (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'"
    )
    head_inject = (
        '<meta charset="utf-8">\n'
        '        <meta http-equiv="Content-Security-Policy" content="{}">\n'
        '        <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '        <title>{}</title>'.format(csp, TITLE)
    )
    html = html.replace('<meta charset="utf-8">', head_inject, 1)
    # 2b) retire les includes Bootstrap (beta3 abandonnee depuis 2021, et de
    #     toute facon quasi inutilisee : seules les classes card/card-body, qui
    #     restent decoratives). Une dependance CDN figee sur une beta est une
    #     surface d'attaque inutile.
    html = re.sub(
        r'\s*<link\b[^>]*bootstrap@[^>]*?/?>',
        "", html, count=1, flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(
        r'\s*<script\b[^>]*bootstrap@[^>]*?>\s*</script>',
        "", html, count=1, flags=re.IGNORECASE | re.DOTALL,
    )
    # 3) coupe la physique une fois le graphe stabilise (perf)
    anchor = "document.getElementById('bar').style.width = '496px';"
    _require(html, anchor, "fin de stabilisation")
    if "physics:false" not in html:
        html = html.replace(
            anchor,
            anchor + "\n                          // Coupe la physique une fois stabilise (perf)"
                     "\n                          network.setOptions({physics:false});",
            1,
        )
    # 4) cable la mise en evidence du voisinage au clic (code rendu fonctionnel)
    net_anchor = "network = new vis.Network(container, data, options);"
    _require(html, net_anchor, "creation du reseau vis")
    html = html.replace(
        net_anchor,
        net_anchor + '\n\n                  network.on("click", neighbourhoodHighlight);',
        1,
    )
    # 5) panneau de fonctionnalites (filtres, recherche, details, stats,
    #    legende, coloration par attribut, export, periode, profondeur).
    palette = {t: color for t, (color, _size) in TYPE_STYLE.items()}
    feature_js = (
        FEATURE_JS
        .replace("__PALETTE__", json.dumps(palette, ensure_ascii=False))
        .replace("__PRIORITY__", json.dumps(PRIORITY_PALETTE, ensure_ascii=False))
    )
    injection = HIGHLIGHT_JS + FEATURE_CSS + FEATURE_HTML + feature_js
    _require(html, "</body>", "fermeture du body")
    html = html.replace("</body>", injection + "\n    </body>", 1)
    return html


def main():
    net = build_network()
    # generate_html() rend le HTML sans tenter d'ouvrir un navigateur
    html = net.generate_html(notebook=False)
    html = _postprocess(html)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("Genere : {} ({} octets)".format(OUTPUT_HTML, len(html)))


if __name__ == "__main__":
    main()
