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
        } else if (highlightActive) {
          for (var id2 in all) {
            all[id2].color = nodeColors[id2];
            if (all[id2].hiddenLabel !== undefined) {
              all[id2].label = all[id2].hiddenLabel;
              all[id2].hiddenLabel = undefined;
            }
          }
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


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _node_tooltip(row):
    """Construit un tooltip en TEXTE BRUT (aucune balise -> aucun risque XSS)."""
    lines = [
        row.get("label", row["id"]),
        "Type : {}".format(row.get("type", "")),
        "Attribut 1 : {}".format(row.get("attribute1", "")),
        "Attribut 2 : {}".format(row.get("attribute2", "")),
        "Attribut 3 : {}".format(row.get("attribute3", "")),
    ]
    return "\n".join(lines)


def build_network():
    net = Network(
        height="850px",
        width="100%",
        bgcolor="#0f1117",
        font_color="#ffffff",
        directed=True,
    )

    node_rows = _read_csv(NODES_CSV)
    if MAX_NODES is not None:
        node_rows = node_rows[:MAX_NODES]

    for row in node_rows:
        color, size = TYPE_STYLE.get(row.get("type"), DEFAULT_STYLE)
        net.add_node(
            row["id"],
            label=row.get("label", row["id"]),
            title=_node_tooltip(row),
            color=color,
            size=size,
            shape="dot",
            group=row.get("type", "autre"),
        )

    node_ids = {row["id"] for row in node_rows}
    for row in _read_csv(EDGES_CSV):
        src, dst = row["source"], row["target"]
        if src not in node_ids or dst not in node_ids:
            continue  # ignore les aretes orphelines
        try:
            weight = float(row.get("weight", 1) or 1)
        except ValueError:
            weight = 1.0
        net.add_edge(
            src, dst,
            title="{} (poids : {:g})".format(row.get("relation", ""), weight),
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
