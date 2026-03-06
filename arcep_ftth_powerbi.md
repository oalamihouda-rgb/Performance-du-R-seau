# 📊 ARCEP FttH — Guide Power BI
## Modèle de données · Power Query · DAX · Pages rapport

---

## 1. ARCHITECTURE — STAR SCHEMA

```
┌──────────────────────────────────────────────────────────────┐
│                       STAR SCHEMA                            │
│                                                              │
│  DIM_Departements ──────────────────────┐                    │
│  (code_dept, nom, region, code_region)  │                    │
│                                         ├──→ FACT_Dept        │
│  DIM_Trimestre ────────────────────────┤    (table de faits)  │
│  (trimestre, annee, num_trim, label)    │                    │
│                                         │                    │
│  DIM_StatutPlan ───────────────────────┘                    │
│  (seuil, libelle, couleur_hex)                               │
└──────────────────────────────────────────────────────────────┘
```

**Connexion** : Power BI Desktop → Obtenir des données → SQLite
→ Pointer vers `output/arcep_ftth.db`
→ Importer : `dept_deploiement`, `region_deploiement`, `historique_national`

---

## 2. POWER QUERY M — TABLES DIMENSION

### DIM_Departements
```m
let
    Source = Csv.Document(File.Contents("output/arcep_dept_analyse.csv"),
             [Delimiter=";", Encoding=65001]),
    Headers = Table.PromoteHeaders(Source),
    AddNom = Table.AddColumn(Headers, "nom_dept", each
        Record.Field([
            #"01"="Ain", #"02"="Aisne", #"03"="Allier", #"04"="Alpes-de-Haute-Provence",
            #"05"="Hautes-Alpes", #"06"="Alpes-Maritimes", #"07"="Ardèche",
            #"11"="Île-de-France (rég.)", #"13"="Bouches-du-Rhône", #"14"="Calvados",
            #"33"="Gironde", #"34"="Hérault", #"35"="Ille-et-Vilaine",
            #"44"="Loire-Atlantique", #"59"="Nord", #"67"="Bas-Rhin",
            #"69"="Rhône", #"75"="Paris", #"76"="Seine-Maritime"
            // ... compléter la liste complète
        ], [code_dept], [code_dept])),  // fallback = code
    AddRegion = Table.AddColumn(AddNom, "code_region", each
        if Text.Length([code_dept]) = 2 then
            Text.Start([code_dept], 2)
        else [code_dept])
in AddRegion
```

### DIM_Trimestre
```m
let
    trimestres = {"T1_2025", "T2_2025"},
    tbl = Table.FromList(trimestres, Splitter.SplitByNothing()),
    renamed = Table.RenameColumns(tbl, {{"Column1", "trimestre_key"}}),
    addLabel = Table.AddColumn(renamed, "label", each
        if [trimestre_key] = "T1_2025" then "T1 2025 (jan–mars)"
        else "T2 2025 (avr–juin)"),
    addOrder = Table.AddColumn(addLabel, "ordre", each
        if [trimestre_key] = "T1_2025" then 1 else 2)
in addOrder
```

---

## 3. MESURES DAX — COMPLÈTES

```dax
// ══════════════════════════════════════════════════════════
// TABLE MESURES : [Mesures_ARCEP]
// Objectif PFTHD 2025 (meilleure estimation France T1 2025)
// ══════════════════════════════════════════════════════════

// ── Constante ─────────────────────────────────────────────
OBJECTIF_PFTHD_2025 =
    44798000  // locaux France entière T1 2025

// ── KPIs de base ──────────────────────────────────────────
Total Raccordables =
    SUM(dept_deploiement[raccordables])

Total Locaux France =
    SUM(dept_deploiement[locaux_totaux])

Raccordables T1 =
    CALCULATE([Total Raccordables],
              dept_deploiement[trimestre] = "T1_2025")

Raccordables T2 =
    CALCULATE([Total Raccordables],
              dept_deploiement[trimestre] = "T2_2025")

// ── Taux ──────────────────────────────────────────────────
Taux Couverture % =
    DIVIDE([Raccordables T2], [OBJECTIF_PFTHD_2025], 0) * 100

Taux Couverture Local % =
    DIVIDE(
        CALCULATE([Total Raccordables], dept_deploiement[trimestre]="T2_2025"),
        CALCULATE([Total Locaux France], dept_deploiement[trimestre]="T2_2025"),
        0
    ) * 100

// ── Évolution ─────────────────────────────────────────────
Delta T1 T2 =
    [Raccordables T2] - [Raccordables T1]

Croissance T1 T2 % =
    DIVIDE([Delta T1 T2], [Raccordables T1], 0) * 100

// ── Objectif PFTHD ────────────────────────────────────────
Progression Objectif % =
    DIVIDE([Raccordables T2], [OBJECTIF_PFTHD_2025], 0) * 100

Ecart Objectif =
    [OBJECTIF_PFTHD_2025] - [Raccordables T2]

// ── Statut département ────────────────────────────────────
Statut Plan =
    VAR taux = [Taux Couverture Local %]
    RETURN
    SWITCH(TRUE(),
        taux >= 95, "🟢 Objectif atteint",
        taux >= 80, "🟡 En bonne voie",
        taux >= 60, "🟠 À surveiller",
        "🔴 Retard critique"
    )

Couleur Statut =
    VAR taux = [Taux Couverture Local %]
    RETURN
    SWITCH(TRUE(),
        taux >= 95, "#1e8449",
        taux >= 80, "#f39c12",
        taux >= 60, "#e67e22",
        "#c0392b"
    )

// ── Indicateurs dynamiques (pour titre visuel) ─────────────
KPI Headline =
    "📡 " & FORMAT([Raccordables T2]/1000000, "0.00") & " M locaux raccordables"
    & " | Couverture " & FORMAT([Taux Couverture %], "0.0") & "% de l'objectif PFTHD"

// ── Rang département ──────────────────────────────────────
Rang Couverture =
    RANKX(
        ALL(dept_deploiement[code_dept]),
        [Taux Couverture Local %],
        , DESC, DENSE
    )

// ── Nb départements par statut ────────────────────────────
Nb Depts Objectif Atteint =
    CALCULATE(
        DISTINCTCOUNT(dept_deploiement[code_dept]),
        FILTER(
            dept_deploiement,
            dept_deploiement[trimestre] = "T2_2025" &&
            DIVIDE(dept_deploiement[raccordables], dept_deploiement[locaux_totaux], 0) >= 0.95
        )
    )

Nb Depts Retard Critique =
    CALCULATE(
        DISTINCTCOUNT(dept_deploiement[code_dept]),
        FILTER(
            dept_deploiement,
            dept_deploiement[trimestre] = "T2_2025" &&
            DIVIDE(dept_deploiement[raccordables], dept_deploiement[locaux_totaux], 0) < 0.60
        )
    )

// ── Série historique ──────────────────────────────────────
Raccordables Historique =
    CALCULATE(
        SUM(historique_national[raccordables]),
        ALLEXCEPT(historique_national, historique_national[trimestre])
    )
```

---

## 4. PLAN DES PAGES RAPPORT

### PAGE 1 — TABLEAU DE BORD NATIONAL
| Visuel | Mesure | Config |
|--------|--------|--------|
| **KPI Card** | `Raccordables T2` | Format : `0,0 " locaux"`, Comparaison T1 |
| **KPI Card** | `Taux Couverture %` | Format : `0.0"%"`, Target = 100% |
| **KPI Card** | `Delta T1 T2` | Format : `+#,0 " locaux"`, couleur conditionnelle |
| **KPI Card** | `Ecart Objectif` | Format : `#,0 " locaux restants"` |
| **Courbe + Aire** | `Raccordables Historique` | Axe X = trimestre (de `historique_national`), Ligne ref = 44 798 000 |
| **Jauge** | `Progression Objectif %` | Min=0, Max=100, Target=100, Valeur = `[Taux Couverture %]` |
| **Anneau** | `Raccordables T2` | Légende = opérateur (si table disponible), Titre = "Parts de marché" |

**Filtres de page** : Aucun (vue nationale)

---

### PAGE 2 — ANALYSE GÉOGRAPHIQUE DÉPARTEMENT
| Visuel | Mesure | Config |
|--------|--------|--------|
| **Carte ArcGIS / Shape Map** | `Taux Couverture Local %` | Carte France départements, Palettе divergente Rouge→Vert |
| **Barres empilées** (horizontal) | `raccordables` + `Ecart Objectif` dept | Top 30 par locaux totaux, empilé raccordé/restant |
| **Matrice** | `Taux`, `Delta`, `Statut Plan` | Ligne = code_dept, formatage conditionnel |
| **Treemap** | `Ecart Objectif` | Affichage retard par département |

**Slicers** : Statut Plan (`[Statut Plan]`), Code région

**Formatage conditionnel matrice** :
```
Règle Taux Couverture Local % :
  ≥ 95  → Fond #1e8449 (vert)
  80–95 → Fond #f39c12 (jaune)
  60–80 → Fond #e67e22 (orange)
  < 60  → Fond #c0392b (rouge)
```

---

### PAGE 3 — ANALYSE RÉGIONALE
| Visuel | Mesure | Config |
|--------|--------|--------|
| **Barres groupées** | `Raccordables T1` + `Raccordables T2` | Axe = code_region, groupé côte à côte |
| **Courbe** | `Taux Couverture Local %` | Axe secondaire, toutes régions |
| **Bullet chart** (via Barre + ligne ref) | `Taux Couverture Local %` vs seuil 95% | |
| **Tableau KPIs** | `r_t1`, `r_t2`, `Delta`, `Croissance %`, `Rang` | Tri interactif |

---

### PAGE 4 — SUIVI PLAN FTTH 2025
| Visuel | Mesure | Config |
|--------|--------|--------|
| **Jauge radiale** | `Progression Objectif %` | Min=0, Max=100, Target=100, rouge sous 80, vert ≥ 95 |
| **Courbe historique** | `raccordables` depuis `historique_national` | Ligne pointillée = objectif PFTHD |
| **KPI** | `Nb Depts Objectif Atteint` + `Nb Depts Retard Critique` | Cards colorées |
| **Barres** | `Ecart Objectif` par département | Tri desc., top 20 retards |
| **Décomposition** (arbre) | `Ecart Objectif` → région → département | |

**Annotation dynamique** :
```dax
Texte Progression =
    "À T2 2025, " & FORMAT([Progression Objectif %],"0.0") &
    "% de l'objectif PFTHD est atteint. Il reste " &
    FORMAT([Ecart Objectif]/1000000,"0.00") &
    " millions de locaux à couvrir."
```

---

## 5. DÉPLOIEMENT ET ACTUALISATION

```
Actualisation trimestrielle :
  1. Télécharger nouveaux fichiers ARCEP (arcep.fr → Données)
  2. Relancer arcep_ftth_analysis.py → met à jour arcep_ftth.db
  3. Power BI Desktop → Actualiser  (ou planifier via Power BI Service)

Publication Power BI Service :
  → Publier workspace → Créer rapport partagé
  → Configurer gateway On-Premises si DB locale
  → Planification actualisation : trimestrielle
```
