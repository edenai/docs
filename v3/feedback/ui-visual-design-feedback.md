# UI Visual Design Feedback — Eden AI V3 Documentation

**Perspective:** UI/UX Designer
**Date:** March 12, 2026
**Scope:** Design visuel, mise en page, hiérarchie, composants — sur la base de la configuration Mintlify actuelle

---

## Résumé

La documentation Eden AI V3 repose sur Mintlify avec une configuration par défaut assez sobre. Le contenu est solide, mais le design manque de personnalité et de chaleur visuelle. On a l'impression d'une documentation générique plutôt que d'un produit qui a une identité forte. Les points les plus impactants à corriger sont : la page d'accueil trop vide, l'absence d'images dans les sections clés, et une palette de couleurs qui n'est pas exploitée au maximum de son potentiel.

---

## 1. Page d'accueil — Le premier contact est raté

### Problème

La page d'accueil actuelle (`index.mdx`) se résume à 4 cartes et une note d'avertissement. C'est fonctionnel mais franchement décevant pour un produit qui donne accès à 200+ modèles d'IA. Stripe, Twilio, ou même des documentations plus modestes comme Resend ou Upstash font bien mieux visuellement dès la landing.

Ce qu'on voit en arrivant :
- Un titre "Documentation"
- Un sous-titre d'une ligne
- 4 cartes basiques
- Une `<Note>` sur la v2 (contenu de maintenance mis en avant)

### Ce qui manque

**a) Un hero avec du contexte visuel**

Mintlify supporte les images hero dans le frontmatter. Les images `hero-light.png` et `hero-dark.png` existent déjà dans `/images/` mais ne sont pas utilisées sur la homepage.

```mdx
---
title: "Eden AI Documentation"
description: "..."
mode: "wide"
---
```

Utiliser `mode: "wide"` et placer les images hero donnerait immédiatement plus d'espace et de respiration.

**b) Une accroche qui dit ce qu'on peut FAIRE**

Le sous-titre actuel : *"Unified access to 200+ AI models — built for developers and teams."*

C'est du marketing, pas de l'orientation. En tant que développeur qui arrive sur la doc, je veux savoir : *"Puis-je utiliser GPT-4o depuis ici ? Quelle est la différence avec l'API OpenAI directe ?"* Ce contexte manque totalement.

**c) La `<Note>` de legacy en position principale**

Placer une note sur la V2 en première position pour les nouveaux utilisateurs est une erreur de hiérarchie. Cela donne l'impression que le produit est en transition chaotique. Cette note devrait être déplacée tout en bas de la page ou dans une section "Migration".

### Recommandation

```mdx
---
title: "Eden AI Documentation"
description: "One API. 200+ AI models. Use any LLM or AI feature — with fallback, routing, and cost tracking built in."
mode: "wide"
---

{/* Section hero avec stats clés */}
<CardGroup cols={3}>
  <Card>**200+** AI Models</Card>
  <Card>**2** Endpoints</Card>
  <Card>**OpenAI-compatible** API</Card>
</CardGroup>

{/* Navigation cards */}
...

{/* Note legacy en bas */}
```

---

## 2. Palette de couleurs — Sous-exploitée

### État actuel

```json
"colors": {
  "primary": "#5386b2",
  "light": "#7ba3ca",
  "dark": "#3d6a91"
}
```

Le bleu `#5386b2` est correct mais très neutre — il ressemble au bleu par défaut de dizaines d'autres docs. Il n'est pas particulièrement mémorable et il contraste peu avec le fond blanc Mintlify.

### Problèmes observés

- **Contraste faible sur fond blanc :** `#5386b2` sur blanc donne un ratio de contraste d'environ 3.1:1 — en dessous du minimum WCAG AA (4.5:1) pour le texte normal.
- **Pas de couleur d'accent secondaire :** Toute la UI repose sur cette seule teinte bleue. Les CTAs, les liens, les icônes — tout est la même couleur.
- **La couleur "dark" sert de fond en mode sombre, mais `#3d6a91` est encore du bleu :** Le mode dark d'Eden AI risque de paraître monochrome (bleu sur fond sombre = peu de contraste et peu d'intérêt visuel).

### Recommandation

Envisager un accent légèrement plus vibrant ou plus saturé, et tester la lisibilité en mode dark :

```json
"colors": {
  "primary": "#3d7cc9",   // Bleu plus saturé, meilleur contraste
  "light": "#6aa3e0",     // Gardé clair pour les fonds légers
  "dark": "#2a5fa8"       // Plus profond pour dark mode
}
```

Alternativement, si l'identité de marque fixe le `#5386b2`, il faut s'assurer que les textes interactifs (liens, CTA) utilisent la variante `dark` plutôt que `primary` pour tenir le contraste.

---

## 3. Densité de navigation — Sidebar surchargée

### Problème

La sidebar affiche en permanence toutes les sections en mode `expanded: true` : Quick Start, Overview, LLMs (12 pages), Expert Models (avec sous-groupes), General, Data Governance, Integrations.

Sur un écran de hauteur standard (768px), l'utilisateur voit une colonne de navigation qui déborde massivement. L'effet est écrasant : tout est visible mais rien n'est prioritaire.

### Ce que ça donne en pratique

Un développeur qui ouvre la doc pour la première fois voit simultanément :
- "Responses", "Chat Completions", "File Upload", "Fallback", "Tools", "Structured Output", "Web Search", "Smart Routing", "Streaming", "Listing Models", "Presets", "Plugins"

C'est la liste d'épicerie complète dès l'entrée. Ça intimide au lieu d'orienter.

### Recommandation

Passer les sections secondaires en `expanded: false` pour laisser respirer la navigation. Seuls Quick Start et Overview méritent d'être ouverts par défaut, parce que ce sont les pages pour les nouveaux arrivants.

```json
{ "group": "LLMs", "expanded": false },
{ "group": "Expert Models", "expanded": false },
{ "group": "General", "expanded": false },
{ "group": "Data Governance", "expanded": false },
{ "group": "Integrations", "expanded": false }
```

La sidebar deviendrait scannable en 3 secondes au lieu de nécessiter un scroll.

---

## 4. Pages de contenu — Hiérarchie visuelle pauvre

### 4.1 Trop de texte brut, pas assez de "vue d'ensemble"

La majorité des pages démarrent avec un paragraphe de texte et un bloc de code. C'est efficace mais monotone. Sur des pages conceptuelles (ai-gateway, universal-ai, llms-vs-expert-models), le texte seul peine à expliquer une architecture.

Les diagrammes Mermaid existants (`ai-gateway.mdx`) sont un bon point de départ, mais ils sont souvent cachés en bas de page plutôt que mis en avant.

**Recommandation :** Sur les pages conceptuelles, placer le diagramme **avant** le texte explicatif. "Show, then tell." Le visuel ancre la compréhension, le texte précise les détails.

### 4.2 Cards trop génériques

Les cartes `<Card>` utilisées en bas de page pour les "Next Steps" ont toutes la même apparence : une icône FontAwesome, un titre, une courte description. Aucune ne se distingue visuellement.

Mintlify supporte des cartes avec `color` (fond coloré) ou `img` (image). Utiliser des couleurs différentes pour les cartes LLM vs Expert Models vs General permettrait de créer une identité visuelle par section :

```mdx
<Card title="Smart Routing" icon="route" color="#3d7cc9" href="...">
  Automatically pick the best model.
</Card>
```

### 4.3 Blocs de code — Taille de police trop petite

Sur certaines pages avec des blocs de code longs (notamment les pages d'intégration LangChain et LibreChat), les blocs sont denses et difficiles à lire. Il n'y a pas de contrôle sur ça côté Mintlify, mais s'assurer que les blocs n'excèdent pas 40-50 lignes avant un `{/* ... */}` collapse aide à la lisibilité.

---

## 5. Mode sombre — Expérience non validée

Mintlify gère le mode sombre automatiquement, mais ça ne veut pas dire que le résultat est bon. Les points de vigilance avec la configuration actuelle :

- **Images hero :** Les fichiers `hero-light.png` et `hero-dark.png` existent, ce qui est bien. S'assurer qu'ils sont correctement déclarés avec `{ "dark": "...", "light": "..." }` si jamais on les utilise.
- **Diagrammes Mermaid :** En mode sombre, les diagrammes Mermaid peuvent avoir un fond blanc qui "flashe" visuellement. Mintlify a une gestion automatique, mais ça mérite une vérification.
- **Couleur primaire en dark mode :** `#7ba3ca` (la variante `light`) est utilisée comme accent en mode sombre — elle peut paraître trop pastel sur fond très sombre.

**Recommandation :** Tester la doc en mode sombre systématiquement sur chaque type de page (texte seul, code, diagramme, tableau) avant de considérer le design validé.

---

## 6. Pages d'intégration — Opportunité visuelle manquée

La section Integrations est l'une des plus fortes commercialement : "utilise le SDK OpenAI que tu connais déjà, change juste l'URL". C'est un argument de vente massif.

Pourtant la page de chaque intégration est... un mur de texte et de code. Pas de logo de l'outil (LangChain, OpenAI, etc.), pas de badge "Compatible", pas de visuel qui dit immédiatement "oui, ça marche avec ton stack".

**Recommandation :**

Ajouter un petit en-tête visuel sur chaque page d'intégration :

```mdx
<CardGroup cols={2}>
  <Card>
    **From:** OpenAI SDK
  </Card>
  <Card>
    **To:** Eden AI (just change the base URL)
  </Card>
</CardGroup>
```

Ou encore mieux, utiliser `<img>` avec les logos officiels des outils intégrés pour une reconnaissance immédiate.

---

## 7. Typographie et espacement

### Ce qui fonctionne
- Le choix de Mintlify garantit une typographie propre et lisible par défaut.
- Les `<CodeGroup>` avec tabs sont bien implémentés et très lisibles.

### Ce qui peut être amélioré

**Espacement entre sections :** Sur des pages longues, les sections s'enchaînent sans assez de respiration. L'usage de `<br />` est présent sur la homepage mais absent des pages de contenu. Des séparateurs visuels (`---`) entre sections logiques majeures aideraient à créer des "pauses" pour le lecteur.

**Hiérarchie des titres :** Sur certaines pages, les `##` et `###` sont utilisés de façon interchangeable pour des niveaux d'importance similaires. Normaliser : `##` pour les étapes ou sections majeures, `###` pour les sous-points.

---

## 8. Micro-interactions et affordances

Ces éléments sont souvent impossibles à contrôler dans Mintlify, mais méritent d'être notés pour une migration éventuelle ou des feedback upstream :

- **Pas de "copy" visual sur les inline code spans** : les blocs de code ont un bouton copier, mais les `inline code` (ex: `feature/subfeature/provider`) n'ont aucune affordance de copie.
- **Les liens dans le texte sont peu visibles** : avec la couleur primaire `#5386b2` sur fond blanc, les liens en corps de texte sont difficilement distinguables du texte normal sans hover. Envisager d'ajouter un `text-decoration: underline` via une personnalisation CSS Mintlify si possible.
- **Pas d'indicateur de "vous êtes ici" visuellement fort** : la page active dans la sidebar est certes mise en évidence, mais subtlement. Pour une doc avec ~50+ pages, un indicateur plus visible (fond coloré sur la page active) aiderait l'orientation.

---

## Récapitulatif des actions design

| Priorité | Action | Impact | Effort |
|----------|--------|--------|--------|
| 🔴 P0 | Enrichir la homepage (hero, stats, repositionner la Note legacy) | Élevé | Faible |
| 🔴 P0 | Passer les sections nav en `expanded: false` sauf Quick Start et Overview | Élevé | Très faible |
| 🟠 P1 | Valider le contraste de couleur en light et dark mode | Moyen | Faible |
| 🟠 P1 | Ajouter des visuels (logos, images) sur les pages Integrations | Élevé | Moyen |
| 🟠 P1 | Mettre les diagrammes Mermaid en haut des pages conceptuelles | Moyen | Faible |
| 🟡 P2 | Utiliser `color` sur les Cards de navigation pour créer une identité par section | Moyen | Faible |
| 🟡 P2 | Ajouter des séparateurs `---` entre sections majeures sur les longues pages | Faible | Très faible |
| 🟡 P2 | Tester et fixer les éventuels problèmes de rendu en dark mode | Moyen | Moyen |
| 🟢 P3 | Ajouter des encadrés visuels "Before/After" ou "SDK comparison" sur les pages Integrations | Élevé | Moyen |

---

## Ce qui est bien et à conserver

- L'usage des `<CodeGroup>` multi-langues est excellent et standardisé sur les bonnes pages.
- Les `<Note>`, `<Tip>`, `<Warning>` sont utilisés correctement là où ils apparaissent.
- La structure Mintlify est propre et la recherche full-text fonctionne bien.
- Les diagrammes Mermaid dans les pages Overview sont une très bonne initiative à étendre.
- Le bouton "Get Started" dans la navbar est bien positionné et visible.

---

*Ce feedback porte uniquement sur la dimension visuelle et la mise en page. Pour les recommandations sur l'architecture d'information et le contenu, voir `ux-feedback-v3.md`.*
