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
import os
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
      function neighbourhoodHighlight(params) {
        var all = nodes.get({ returnType: "Object" });
        if (params.nodes.length > 0) {
          highlightActive = true;
          var selected = params.nodes[0];
          for (var id in all) {
            all[id].color = "rgba(120,120,120,0.25)";
            if (all[id].hiddenLabel === undefined) {
              all[id].hiddenLabel = all[id].label;
              all[id].label = undefined;
            }
          }
          var firstDeg = network.getConnectedNodes(selected);
          var secondDeg = [];
          for (var j = 0; j < firstDeg.length; j++) {
            secondDeg = secondDeg.concat(network.getConnectedNodes(firstDeg[j]));
          }
          for (var k = 0; k < secondDeg.length; k++) {
            all[secondDeg[k]].color = "rgba(160,160,160,0.55)";
            if (all[secondDeg[k]].hiddenLabel !== undefined) {
              all[secondDeg[k]].label = all[secondDeg[k]].hiddenLabel;
              all[secondDeg[k]].hiddenLabel = undefined;
            }
          }
          for (var m = 0; m < firstDeg.length; m++) {
            all[firstDeg[m]].color = nodeColors[firstDeg[m]];
            if (all[firstDeg[m]].hiddenLabel !== undefined) {
              all[firstDeg[m]].label = all[firstDeg[m]].hiddenLabel;
              all[firstDeg[m]].hiddenLabel = undefined;
            }
          }
          all[selected].color = nodeColors[selected];
          if (all[selected].hiddenLabel !== undefined) {
            all[selected].label = all[selected].hiddenLabel;
            all[selected].hiddenLabel = undefined;
          }
          // Aretes : on ne garde en couleur que celles dont les deux extremites
          // font partie du voisinage mis en evidence.
          var keep = {};
          keep[selected] = true;
          for (var f = 0; f < firstDeg.length; f++) { keep[firstDeg[f]] = true; }
          for (var s = 0; s < secondDeg.length; s++) { keep[secondDeg[s]] = true; }
          var edgeUpdates = [];
          var allEdgesObj = edges.get({ returnType: "Object" });
          for (var eid in allEdgesObj) {
            if (!allEdgesObj.hasOwnProperty(eid)) continue;
            var e = allEdgesObj[eid];
            var visible = keep[e.from] === true && keep[e.to] === true;
            edgeUpdates.push({
              id: e.id,
              color: visible ? "#555555" : "rgba(80,80,80,0.12)"
            });
          }
          edges.update(edgeUpdates);
        } else if (highlightActive) {
          for (var id2 in all) {
            all[id2].color = nodeColors[id2];
            if (all[id2].hiddenLabel !== undefined) {
              all[id2].label = all[id2].hiddenLabel;
              all[id2].hiddenLabel = undefined;
            }
          }
          var resetEdges = [];
          var allEdgesObj2 = edges.get({ returnType: "Object" });
          for (var eid2 in allEdgesObj2) {
            if (!allEdgesObj2.hasOwnProperty(eid2)) continue;
            resetEdges.push({ id: allEdgesObj2[eid2].id, color: "#555555" });
          }
          edges.update(resetEdges);
          highlightActive = false;
        }
        var updateArray = [];
        for (var id3 in all) { if (all.hasOwnProperty(id3)) updateArray.push(all[id3]); }
        nodes.update(updateArray);
      }
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
    net = Network(
        height="850px",
        width="100%",
        bgcolor="#0f1117",
        font_color="#ffffff",
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
        net.add_node(
            node_id,
            label=_safe(row.get("label") or node_id),
            title=_node_tooltip(row),
            color=color,
            size=size,
            shape="dot",
            group=row.get("type", "autre"),
        )
        node_ids.add(node_id)

    for row in _read_csv(EDGES_CSV, required=("source", "target")):
        src = _safe((row.get("source") or "").strip())
        dst = _safe((row.get("target") or "").strip())
        if not src or not dst or src not in node_ids or dst not in node_ids:
            continue  # arete orpheline ou incomplete : ignoree
        try:
            weight = float(row.get("weight", 1) or 1)
        except ValueError:
            weight = 1.0
        net.add_edge(
            src, dst,
            title="{} (poids : {:g})".format(_safe(row.get("relation", "")), weight),
            value=weight,
        )

    net.set_options(OPTIONS)
    return net


def _postprocess(html):
    """Applique les correctifs qui ne sont pas exposes par l'API pyvis."""
    # 1) DOCTYPE + lang
    if not html.lstrip().startswith("<!DOCTYPE"):
        html = html.replace("<html>", '<!DOCTYPE html>\n<html lang="fr">', 1)
    # 2) viewport + title dans le <head>
    head_inject = (
        '<meta charset="utf-8">\n'
        '        <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '        <title>{}</title>'.format(TITLE)
    )
    html = html.replace('<meta charset="utf-8">', head_inject, 1)
    # 3) coupe la physique une fois le graphe stabilise (perf)
    anchor = "document.getElementById('bar').style.width = '496px';"
    if anchor in html and "physics:false" not in html:
        html = html.replace(
            anchor,
            anchor + "\n                          // Coupe la physique une fois stabilise (perf)"
                     "\n                          network.setOptions({physics:false});",
            1,
        )
    # 4) cable la mise en evidence du voisinage au clic (code rendu fonctionnel)
    net_anchor = "network = new vis.Network(container, data, options);"
    if net_anchor in html:
        html = html.replace(
            net_anchor,
            net_anchor + '\n\n                  network.on("click", neighbourhoodHighlight);',
            1,
        )
    html = html.replace("</body>", HIGHLIGHT_JS + "\n    </body>", 1)
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
