# Audit destructif KiVendTout — Phase 1 (4 dimensions)

Audit beta-testing impitoyable, 4 auditeurs indépendants (UX, Design, Technique/Responsive,
Métier/Data) sur les 6 dashboards + CSS + JS, croisé avec l'API live `:8000`.
Les défauts qui ressortent dans **plusieurs** audits sont notés ⚠️ (haute confiance).

## 🔴 Défauts CRITIQUES (transverses, confirmés par plusieurs audits)

1. ⚠️ **Navigation cassée** — La page `use_cases` est **orpheline** : absente des 6 barres de
   nav (seule sa propre page la liste). L'Overview a en plus une **double navigation**
   (nav haute + grille « Modules »). *(UX + Design + Tech + Data)*
2. ⚠️ **Surcharge informationnelle** — Identité : **7 sections / ~24 cartes**, scroll infini.
   Fraude : **8 KPIs** empilés avant tout contenu. Transferts : même hiérarchie répétée 3×.
   Aucun KPI « héros », tout a la même taille → l'œil ne sait où se poser. *(UX)*
3. ⚠️ **Design fragmenté** — La « carte » est réinventée **8 fois** (rayons 14/18/20/22px,
   paddings 13/18/20/22px), `font-weight:900` partout (plus aucune hiérarchie), **~18 tailles
   de police** quasi-jumelles, **aucun token d'espacement**, **3 rouges « danger » différents**
   (#c45454 / #cb5a61 / rgb(203,90,97)). Cause racine : chaque page redéfinit ses styles inline. *(Design)*
4. ⚠️ **Responsive 3/10** — Cassure brutale à 980px, **zone tablette 560–980px non couverte**.
   `min-width:440px` sur la heatmap → scroll horizontal mobile ; grilles `repeat(2|3,…)` et
   `minmax(320px,…)` rigides ; largeurs fixes en px. *(Tech)*
5. ⚠️ **Performance** — **Triple polling concurrent à 1 s** (setInterval page + SSE + ops) →
   jusqu'à **~12 requêtes/s par onglet** à vide, re-render `innerHTML` complet chaque seconde
   (perd la sélection en cours, scintille), aucune pause sur onglet masqué. *(Tech + UX)*
6. **Incohérence des données fraude** — 3 sources se contredisent d'un facteur ~200 :
   `/api/stats` = **1** paiement frauduleux ; data-lake gold = **224** ; analytics = **2211**
   alertes. Le live est daté du 2026-06-22, le lake figé au 2026-03-18, juxtaposés sans légende. *(Data)*

## 🟠 Défauts MAJEURS

**Métier / Data**
- **3630 alertes pour 1 fraude confirmée** non contextualisé sur les cartes (sur-déclenchement
  massif des règles ; l'API expose pourtant `/api/kpis/readable` avec l'interprétation, sous-exploité).
- **Analytics affiché « ABSENT »** alors que le rapport warehouse est **PASS 9/9 (100 %)** —
  l'écran lit `live.schema_exists` au lieu de `latest_report.status`.
- **Sélecteur « Fenêtre » (Typologies) mort** : `?window_hours=X` est ignoré par l'API, rien ne change.
- **« % du volume »** calculé sur 4 motifs **non-exclusifs** (Σ motifs 8171 > 3630 alertes) → part > 100 % possible.
- **Contradiction micro-batch** (Transferts) : hero « présent (14 fenêtres) » vs panneau « 0 fenêtre / 24h ».
- **Checkout 24h tout à 0** mais 60 cartes + 12 mineurs affichés (fenêtre temporelle non indiquée ;
  l'historique réel = 412 blocages mineurs).

**UX / Design**
- **Langue FR/EN mélangée** par mot : eyebrows « Fraud operations / Signal breakdown », pills
  « Sparkline / Live / Split », libellés « Verified / Reject if Adult »…
- **Noms de classes CSS affichés comme libellés** : badge « cool » / « danger » / « success » montré à l'utilisateur (`id_cards:874`).
- **`prompt()` / `alert()` / `confirm()` natifs** pour les décisions analyste (approuver/bloquer,
  saisie d'identité) — bloquant, non stylé ; l'identité opérateur est redemandée alors qu'un champ existe déjà.
- **Bloc « config notifications » (SMTP, toggles, historique)** insère une page de réglages au milieu
  du flux opérationnel fraude, avant la file d'alertes.
- **Commande shell `bash scripts/run_micro_batch.sh once`** affichée dans l'UI métier.
- **États « - » ambigus** (chargement = vide = erreur), pas de skeleton ; erreurs API parfois silencieuses.
- **Header non unifié** : `index` invente son propre header au lieu du `.masthead` commun.

**Technique**
- **`@media` binaire** (3 breakpoints, tous à 980px) ; `body padding:28px` non réduit avant 980px.
- **Focus `:focus-visible` quasi absent** (a11y) ; contraste `--ink-760` ≈ 4.0:1 sous le seuil AA.
- **Duplication JS massive** : `escapeHtml`, `fmtNumber`, config API, bootstrap live_sync copiés-collés
  dans 5-6 pages → dérive garantie (c'est la cause mécanique des incohérences de libellés).
- **`Promise.all` « tout ou rien »** : un endpoint secondaire en erreur noircit tout le dashboard
  (le pattern robuste `allSettled` n'existe que sur `index`).
- **`onclick="fn('${escapeHtml(key)}')"`** : échappement HTML mais pas contexte attribut JS → XSS résiduel.

## 🟡 Défauts MINEURS (extraits)
- Bug `var(--ink-700)` **inexistant** (`use_cases:277`, `transfer:470`) → couleur de statut invalide.
- `body::before { display:none }` mort ; règle CSS vestige.
- « Hash stored : Oui » **codé en dur** (`id_cards:590`), contredit le hash « - » au-dessus.
- Boutons « Actualiser » manuels **inutiles** vu l'auto-refresh 1 s.
- `Math.min(...[])` = `Infinity` si liste vide (`id_cards:637`).
- Orbe vocale présente sur toutes les pages même si le service `:8100` est down (pas de health-check).

## 🎯 Plan de priorités V2 (ordre d'exécution)

| # | Action | Défauts traités |
|---|---|---|
| 1 | **Design system unifié** (tokens espace/typo/rayon/couleur, 1 `.card`, `.badge`, `.btn`, focus) | 3, design |
| 2 | **JS commun partagé** (`dashboard_common.js` : nav unique + Use cases, utils, modale, polling 15 s + pause onglet) | 1, 5, perf, duplication |
| 3 | **Responsive mobile-first** (`auto-fit/minmax` partout, suppr. largeurs fixes, heatmap) | 4 |
| 4 | **Dégraissage des pages** (4 KPIs max + 1 héros, sections fusionnées, config notif → Paramètres) | 2 |
| 5 | **Corrections data** (Analytics PASS, ratio alertes/fraude, fenêtres datées, motifs non-exclusifs) | 6, métier |
| 6 | **Finitions** (langue unifiée, fin des `prompt()`, libellés métier, suppr. jargon/shell, états chargement) | UX, mineurs |
