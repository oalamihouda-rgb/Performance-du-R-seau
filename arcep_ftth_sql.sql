-- =============================================================================
-- ARCEP FttH — Schéma SQL + Requêtes analytiques
-- Cible : SQLite / PostgreSQL / SQL Server
-- Données réelles : 2025 T1 & T2 — Feuilles 'FttH par Départements' et 'FttH par Régions'
-- =============================================================================


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 1 — SCHÉMA RELATIONNEL
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS dept_deploiement (
    code_dept               CHAR(3)   NOT NULL,   -- Code INSEE département (01..976)
    locaux_totaux           REAL,                  -- Meilleure estimation locaux INSEE
    raccordables_T_prev     INTEGER,               -- Raccordables trimestre précédent
    raccordables            INTEGER,               -- Raccordables trimestre courant
    trimestre               VARCHAR(10) NOT NULL,  -- 'T1_2025' ou 'T2_2025'
    PRIMARY KEY (code_dept, trimestre)
);

CREATE TABLE IF NOT EXISTS region_deploiement (
    code_region             CHAR(3)   NOT NULL,   -- Code INSEE région
    locaux_totaux           REAL,
    raccordables_T_prev     INTEGER,
    raccordables            INTEGER,
    trimestre               VARCHAR(10) NOT NULL,
    PRIMARY KEY (code_region, trimestre)
);

CREATE TABLE IF NOT EXISTS historique_national (
    trimestre               VARCHAR(10) PRIMARY KEY,
    raccordables            INTEGER,
    progression_objectif_   REAL        -- % vs PFTHD
);

CREATE TABLE IF NOT EXISTS referentiel_oi (
    code_oi                 VARCHAR(10) PRIMARY KEY,
    maison_mere             VARCHAR(100),
    nom_exploitant          VARCHAR(200),
    code_interop            VARCHAR(20),
    zone_couverture         VARCHAR(100),
    ztd                     BOOLEAN,
    zmd                     BOOLEAN,
    rip                     BOOLEAN,
    pfthd                   BOOLEAN
);

-- Indexes pour la performance
CREATE INDEX IF NOT EXISTS idx_dept_trim    ON dept_deploiement(trimestre);
CREATE INDEX IF NOT EXISTS idx_region_trim  ON region_deploiement(trimestre);


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 2 — REQUÊTES ANALYTIQUES
-- ═══════════════════════════════════════════════════════════════════════════════


-- ─── Q1 : KPIs nationaux par trimestre ──────────────────────────────────────
-- Réplique du tableau de bord ARCEP agrégé
SELECT
    trimestre,
    SUM(raccordables)                                           AS total_raccordables,
    ROUND(SUM(raccordables) / 44798000.0 * 100, 2)            AS taux_objectif_pfthd_pct,
    44798000 - SUM(raccordables)                               AS ecart_objectif,
    COUNT(DISTINCT code_dept)                                  AS nb_departements_actifs
FROM dept_deploiement
GROUP BY trimestre
ORDER BY trimestre;


-- ─── Q2 : Évolution T1→T2 par département (delta + croissance) ──────────────
WITH t1 AS (
    SELECT code_dept, raccordables AS r_t1, locaux_totaux
    FROM dept_deploiement WHERE trimestre = 'T1_2025'
),
t2 AS (
    SELECT code_dept, raccordables AS r_t2
    FROM dept_deploiement WHERE trimestre = 'T2_2025'
)
SELECT
    t2.code_dept,
    t1.locaux_totaux,
    t1.r_t1                                                    AS raccordables_t1,
    t2.r_t2                                                    AS raccordables_t2,
    (t2.r_t2 - t1.r_t1)                                       AS delta_absolu,
    ROUND((t2.r_t2 - t1.r_t1) * 100.0 / NULLIF(t1.r_t1, 0), 2) AS croissance_pct,
    ROUND(t2.r_t2 * 100.0 / NULLIF(t1.locaux_totaux, 0), 2)  AS taux_couverture_t2_pct,
    ROUND(t1.locaux_totaux - t2.r_t2, 0)                      AS retard_objectif
FROM t1
JOIN t2 ON t1.code_dept = t2.code_dept
ORDER BY croissance_pct DESC;


-- ─── Q3 : Classement départements — couverture T2 2025 avec statut plan ──────
SELECT
    code_dept,
    raccordables,
    ROUND(raccordables * 100.0 / NULLIF(locaux_totaux, 0), 2)  AS taux_couverture_pct,
    ROUND(locaux_totaux - raccordables, 0)                      AS retard_locaux,
    CASE
        WHEN raccordables * 100.0 / NULLIF(locaux_totaux, 0) >= 95 THEN '🟢 ≥ 95% — Objectif atteint'
        WHEN raccordables * 100.0 / NULLIF(locaux_totaux, 0) >= 80 THEN '🟡 80–95% — En bonne voie'
        WHEN raccordables * 100.0 / NULLIF(locaux_totaux, 0) >= 60 THEN '🟠 60–80% — À surveiller'
        ELSE                                                         '🔴 < 60%  — Retard significatif'
    END                                                         AS statut_plan
FROM dept_deploiement
WHERE trimestre = 'T2_2025'
ORDER BY taux_couverture_pct DESC;


-- ─── Q4 : Analyse régionale comparative T1→T2 ───────────────────────────────
WITH reg_evo AS (
    SELECT
        r1.code_region,
        r1.raccordables                                        AS r_t1,
        r2.raccordables                                        AS r_t2,
        r1.locaux_totaux,
        (r2.raccordables - r1.raccordables)                    AS delta,
        ROUND((r2.raccordables - r1.raccordables) * 100.0
              / NULLIF(r1.raccordables, 0), 2)                 AS croissance_pct,
        ROUND(r2.raccordables * 100.0
              / NULLIF(r1.locaux_totaux, 0), 2)               AS taux_couverture_t2
    FROM region_deploiement r1
    JOIN region_deploiement r2 ON r1.code_region = r2.code_region
    WHERE r1.trimestre = 'T1_2025' AND r2.trimestre = 'T2_2025'
)
SELECT *,
    RANK() OVER (ORDER BY taux_couverture_t2 DESC)             AS rang_couverture,
    RANK() OVER (ORDER BY croissance_pct DESC)                 AS rang_croissance
FROM reg_evo
WHERE r_t1 > 0
ORDER BY taux_couverture_t2 DESC;


-- ─── Q5 : Détection des départements en retard critique ─────────────────────
-- Départements sous 70% de couverture avec plus de 50k locaux à couvrir
SELECT
    t2.code_dept,
    t2.raccordables,
    t2.locaux_totaux,
    ROUND(t2.raccordables * 100.0 / NULLIF(t2.locaux_totaux, 0), 2)  AS taux_pct,
    ROUND(t2.locaux_totaux - t2.raccordables, 0)                      AS gap_locaux,
    ROUND((t2.raccordables - t1.raccordables) * 100.0
          / NULLIF(t1.raccordables, 0), 2)                            AS croissance_trim_pct
FROM dept_deploiement t2
JOIN dept_deploiement t1
  ON t1.code_dept = t2.code_dept AND t1.trimestre = 'T1_2025'
WHERE t2.trimestre = 'T2_2025'
  AND t2.raccordables * 100.0 / NULLIF(t2.locaux_totaux, 0) < 70
  AND (t2.locaux_totaux - t2.raccordables) > 50000
ORDER BY gap_locaux DESC;


-- ─── Q6 : Suivi progression historique nationale vers PFTHD ─────────────────
SELECT
    trimestre,
    raccordables,
    ROUND(raccordables / 44798000.0 * 100, 2)                  AS progression_pct,
    raccordables - LAG(raccordables) OVER (ORDER BY trimestre)  AS delta_vs_trim_prec,
    ROUND(
        (raccordables - LAG(raccordables) OVER (ORDER BY trimestre)) * 100.0
        / NULLIF(LAG(raccordables) OVER (ORDER BY trimestre), 0),
    2)                                                           AS croissance_trim_pct
FROM historique_national
ORDER BY trimestre;


-- ─── Q7 : Vue Power BI — Table analytique complète ──────────────────────────
-- (Matérialisée comme VIEW ou table temporaire selon le moteur)
CREATE VIEW IF NOT EXISTS v_dept_kpis AS
WITH evo AS (
    SELECT
        t1.code_dept,
        t1.locaux_totaux,
        t1.raccordables                                         AS raccordables_t1,
        t2.raccordables                                         AS raccordables_t2,
        t2.raccordables - t1.raccordables                       AS delta_t1_t2,
        ROUND((t2.raccordables - t1.raccordables) * 100.0
              / NULLIF(t1.raccordables, 0), 2)                  AS croissance_pct,
        ROUND(t2.raccordables * 100.0
              / NULLIF(t1.locaux_totaux, 0), 2)                 AS taux_couverture_pct
    FROM dept_deploiement t1
    JOIN dept_deploiement t2 ON t1.code_dept = t2.code_dept
    WHERE t1.trimestre = 'T1_2025' AND t2.trimestre = 'T2_2025'
)
SELECT
    *,
    ROUND(raccordables_t2 * 100.0 / 44798000.0 * (locaux_totaux /
        (SELECT SUM(locaux_totaux) FROM dept_deploiement WHERE trimestre='T2_2025')), 2)
                                                                AS contrib_objectif_national_pct,
    CASE
        WHEN taux_couverture_pct >= 95 THEN 1
        WHEN taux_couverture_pct >= 80 THEN 2
        WHEN taux_couverture_pct >= 60 THEN 3
        ELSE 4
    END                                                         AS rang_statut,
    CASE
        WHEN taux_couverture_pct >= 95 THEN '🟢 ≥ 95%'
        WHEN taux_couverture_pct >= 80 THEN '🟡 80–95%'
        WHEN taux_couverture_pct >= 60 THEN '🟠 60–80%'
        ELSE                                 '🔴 < 60%'
    END                                                         AS statut_plan
FROM evo
ORDER BY taux_couverture_pct DESC;
