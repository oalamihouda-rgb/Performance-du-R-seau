"""
=============================================================================
ARCEP — Analyse déploiement FttH  |  Python ETL + Analyses + Exports
Objectifs : Analyse géographique (régions/départements) + Couverture vs Plan FTTH
=============================================================================
"""
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
DATA_DIR  = Path("data/")         # Adapter selon votre arborescence
OUT_DIR   = Path("output/")
OUT_DIR.mkdir(exist_ok=True)

FILE_T1  = DATA_DIR / "2025t1-obs-hd-thd-deploiement-vf.xlsx"
FILE_T2  = DATA_DIR / "2025t2-obs-hd-thd-deploiement-vf.xlsx"
FILE_REF = DATA_DIR / "referentiel-operateurs-infrastructure-ftth-2025-07.xlsx"

# Objectif Plan France Très Haut Débit 2025
OBJECTIF_PFTHD = 44_798_000  # Meilleure estimation T1 2025 locaux France entière


# ═══════════════════════════════════════════════════════════════════════════════
# BLOC 1 — EXTRACTION / TRANSFORMATION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_dept(filepath: Path, trimestre: str) -> pd.DataFrame:
    """Extrait les données FttH par département (feuille 'FttH par Départements')."""
    raw = pd.read_excel(filepath, sheet_name='FttH par Départements', header=None)
    raw.columns = raw.iloc[4].tolist()          # row 4 = en-têtes réels
    data = raw.iloc[5:].copy()
    data.columns = [str(c) for c in data.columns]
    data = data[data.iloc[:, 1] == 'Locaux Raccordables'].copy()

    col_code      = data.columns[0]   # 'Code département'
    col_champ     = data.columns[1]   # 'Champ'
    col_estimation= data.columns[2]   # 'Meilleure estimation des locaux'
    col_last      = data.columns[-1]  # Trimestre courant
    col_prev      = data.columns[-2]  # Trimestre précédent

    out = data[[col_code, col_estimation, col_prev, col_last]].copy()
    out.columns = ['code_dept', 'locaux_totaux', 'raccordables_T_prev', 'raccordables']
    out['trimestre'] = trimestre

    out['code_dept'] = out['code_dept'].astype(str).str.strip().str.zfill(2)
    for c in ['locaux_totaux', 'raccordables_T_prev', 'raccordables']:
        out[c] = pd.to_numeric(out[c], errors='coerce')
    return out.dropna(subset=['raccordables'])


def extract_region(filepath: Path, trimestre: str) -> pd.DataFrame:
    """Extrait les données FttH par région (feuille 'FttH par Régions')."""
    raw = pd.read_excel(filepath, sheet_name='FttH par Régions', header=None)
    raw.columns = raw.iloc[4].tolist()
    data = raw.iloc[5:].copy()
    data.columns = [str(c) for c in data.columns]
    data = data[data.iloc[:, 1] == 'Locaux Raccordables'].copy()

    col_code      = data.columns[0]
    col_estimation= data.columns[2]
    col_last      = data.columns[-1]
    col_prev      = data.columns[-2]

    out = data[[col_code, col_estimation, col_prev, col_last]].copy()
    out.columns = ['code_region', 'locaux_totaux', 'raccordables_T_prev', 'raccordables']
    out['trimestre'] = trimestre

    for c in ['locaux_totaux', 'raccordables_T_prev', 'raccordables']:
        out[c] = pd.to_numeric(out[c], errors='coerce')
    return out.dropna(subset=['raccordables'])


def extract_national_series(filepath: Path) -> pd.DataFrame:
    """Extrait la série historique nationale (feuille 'FttH')."""
    raw  = pd.read_excel(filepath, sheet_name='FttH', header=None)
    qtrs = [str(q).strip() for q in raw.iloc[1, 1:].tolist()]
    rows_data = []
    for i in range(4, len(raw)):
        label = raw.iloc[i, 0]
        if pd.notna(label) and str(label).strip() not in ['', 'nan']:
            vals = raw.iloc[i, 1:].tolist()
            rows_data.append({'indicateur': str(label).strip(), **dict(zip(qtrs, vals))})
    df = pd.DataFrame(rows_data)
    return df


def extract_couverture(filepath: Path) -> pd.DataFrame:
    """Extrait les taux de couverture par grande zone (feuille 'Couverture')."""
    raw = pd.read_excel(filepath, sheet_name='Couverture', header=None)
    qtrs = [str(q).strip() for q in raw.iloc[3, 1:].tolist()]
    rows_data = []
    for i in range(4, len(raw)):
        label = raw.iloc[i, 0]
        if pd.notna(label) and str(label).strip() not in ['', 'nan']:
            vals = raw.iloc[i, 1:].tolist()
            rows_data.append({'zone': str(label).strip(), **dict(zip(qtrs, vals))})
    return pd.DataFrame(rows_data)


def extract_referentiel(filepath: Path) -> pd.DataFrame:
    """Charge le référentiel des opérateurs."""
    df = pd.read_excel(filepath, sheet_name='OI FttH')
    df.columns = (df.columns.str.strip()
                             .str.lower()
                             .str.replace(r'\s+', '_', regex=True)
                             .str.replace(r'[\n/]', '_', regex=True))
    return df


# ─── Chargement ───────────────────────────────────────────────────────────────
print("📥  Chargement des fichiers ARCEP...")
dept_t1    = extract_dept(FILE_T1, 'T1_2025')
dept_t2    = extract_dept(FILE_T2, 'T2_2025')
reg_t1     = extract_region(FILE_T1, 'T1_2025')
reg_t2     = extract_region(FILE_T2, 'T2_2025')
nat_series = extract_national_series(FILE_T2)   # T2 = plus récent
couverture = extract_couverture(FILE_T1)
df_ref     = extract_referentiel(FILE_REF)

# Fusion T1+T2
dept_all = pd.concat([dept_t1, dept_t2], ignore_index=True)
reg_all  = pd.concat([reg_t1,  reg_t2],  ignore_index=True)

print(f"  ✅ Départements : {len(dept_all)} lignes ({len(dept_t1)} T1 + {len(dept_t2)} T2)")
print(f"  ✅ Régions      : {len(reg_all)} lignes")
print(f"  ✅ Référentiel  : {len(df_ref)} opérateurs")


# ═══════════════════════════════════════════════════════════════════════════════
# BLOC 2 — CALCULS ANALYTIQUES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 2.1 KPIs nationaux ────────────────────────────────────────────────────────
# Ligne total national T1 2025 depuis la série historique
nat_total = nat_series[nat_series['indicateur'].str.startswith('Total des locaux raccordables')]
val_t1 = float(nat_total.iloc[0]['2025 T1'])
val_t2 = float(nat_total.iloc[0]['2025 T2'])

kpis = {
    'Raccordables T1 2025':    val_t1,
    'Raccordables T2 2025':    val_t2,
    'Delta T1→T2':             val_t2 - val_t1,
    'Croissance %':            round((val_t2 - val_t1) / val_t1 * 100, 2),
    'Objectif PFTHD 2025':     OBJECTIF_PFTHD,
    'Taux couverture T2 %':    round(val_t2 / OBJECTIF_PFTHD * 100, 2),
    'Écart objectif':          OBJECTIF_PFTHD - val_t2,
}
print("\n📊  KPIs Nationaux :")
for k, v in kpis.items():
    print(f"    {k:<30} : {v:>15,.0f}")


# ── 2.2 Analyse départementale ────────────────────────────────────────────────
dept_pivot = dept_t2.copy()
dept_pivot = dept_pivot.merge(
    dept_t1[['code_dept','raccordables']].rename(columns={'raccordables':'raccordables_t1'}),
    on='code_dept', how='left'
)
dept_pivot['taux_couverture_%']  = (dept_pivot['raccordables'] / dept_pivot['locaux_totaux'] * 100).round(2)
dept_pivot['delta_raccordables'] = (dept_pivot['raccordables'] - dept_pivot['raccordables_t1']).round(0)
dept_pivot['croissance_%']       = ((dept_pivot['raccordables'] - dept_pivot['raccordables_t1']) /
                                    dept_pivot['raccordables_t1'].replace(0, np.nan) * 100).round(2)
dept_pivot['retard_objectif']    = (dept_pivot['locaux_totaux'] - dept_pivot['raccordables']).round(0)
dept_pivot['statut_plan']        = dept_pivot['taux_couverture_%'].apply(
    lambda x: '🟢 ≥ 95%' if x >= 95 else ('🟡 80–95%' if x >= 80 else ('🟠 60–80%' if x >= 60 else '🔴 < 60%'))
)
dept_pivot.sort_values('taux_couverture_%', ascending=False, inplace=True)

# ── 2.3 Analyse régionale ─────────────────────────────────────────────────────
reg_pivot = reg_t2.copy()
reg_pivot = reg_pivot.merge(
    reg_t1[['code_region','raccordables']].rename(columns={'raccordables':'raccordables_t1'}),
    on='code_region', how='left'
)
reg_pivot['taux_couverture_%']  = (reg_pivot['raccordables'] / reg_pivot['locaux_totaux'] * 100).round(2)
reg_pivot['delta_raccordables'] = (reg_pivot['raccordables'] - reg_pivot['raccordables_t1']).round(0)
reg_pivot['croissance_%']       = ((reg_pivot['raccordables'] - reg_pivot['raccordables_t1']) /
                                    reg_pivot['raccordables_t1'].replace(0, np.nan) * 100).round(2)
reg_pivot.sort_values('taux_couverture_%', ascending=False, inplace=True)

# ── 2.4 Série historique agrégée (2019→2025) ─────────────────────────────────
nat_row = nat_series[nat_series['indicateur'].str.startswith('Total des locaux raccordables')].iloc[0]
hist_cols = [c for c in nat_row.index if c not in ['indicateur'] and
             any(yr in str(c) for yr in ['2019','2020','2021','2022','2023','2024','2025'])]
hist = pd.DataFrame({
    'trimestre':      hist_cols,
    'raccordables':   [pd.to_numeric(nat_row[c], errors='coerce') for c in hist_cols]
}).dropna()
hist['progression_objectif_%'] = (hist['raccordables'] / OBJECTIF_PFTHD * 100).round(2)

# ── 2.5 Opérateurs nationaux (T2 2025) ───────────────────────────────────────
op_rows = nat_series[nat_series['indicateur'].str.contains(
    r'Orange|Altice|Iliad|Autres OI', regex=True, na=False
)][['indicateur', '2025 T1', '2025 T2']].copy()
op_rows.columns = ['operateur', 'raccordables_t1', 'raccordables_t2']
for c in ['raccordables_t1', 'raccordables_t2']:
    op_rows[c] = pd.to_numeric(op_rows[c], errors='coerce')
# Filter to France total rows (not zone-level duplicates) = rows without "ZTD" context
op_national = op_rows.iloc[:4].copy()  # 4 opérateurs agrégés nationaux
total_t2_ops = op_national['raccordables_t2'].sum()
op_national['part_marche_%'] = (op_national['raccordables_t2'] / total_t2_ops * 100).round(1)
op_national['delta'] = op_national['raccordables_t2'] - op_national['raccordables_t1']

print("\n🏢  Opérateurs nationaux T2 2025 :")
print(op_national.to_string(index=False))

print("\n📍  Top 10 départements par taux de couverture (T2 2025) :")
print(dept_pivot[['code_dept','taux_couverture_%','raccordables','locaux_totaux','statut_plan']].head(10).to_string(index=False))

print("\n⚠️   10 départements les plus en retard (T2 2025) :")
print(dept_pivot.tail(10)[['code_dept','taux_couverture_%','raccordables','retard_objectif','statut_plan']].to_string(index=False))


# ═══════════════════════════════════════════════════════════════════════════════
# BLOC 3 — EXPORTS (CSV + SQLite)
# ═══════════════════════════════════════════════════════════════════════════════
import sqlite3

# ─── Exports CSV ──────────────────────────────────────────────────────────────
dept_all.to_csv(OUT_DIR / 'arcep_ftth_dept.csv',       sep=';', index=False, encoding='utf-8-sig')
reg_all.to_csv(OUT_DIR  / 'arcep_ftth_region.csv',     sep=';', index=False, encoding='utf-8-sig')
dept_pivot.to_csv(OUT_DIR / 'arcep_dept_analyse.csv',  sep=';', index=False, encoding='utf-8-sig')
reg_pivot.to_csv(OUT_DIR  / 'arcep_reg_analyse.csv',   sep=';', index=False, encoding='utf-8-sig')
hist.to_csv(OUT_DIR / 'arcep_historique_national.csv', sep=';', index=False, encoding='utf-8-sig')
op_national.to_csv(OUT_DIR / 'arcep_operateurs.csv',   sep=';', index=False, encoding='utf-8-sig')

# ─── Export SQLite ────────────────────────────────────────────────────────────
db_path = str(OUT_DIR / 'arcep_ftth.db')
conn = sqlite3.connect(db_path)
dept_all.to_sql('dept_deploiement',   conn, if_exists='replace', index=False)
reg_all.to_sql('region_deploiement',  conn, if_exists='replace', index=False)
dept_pivot.to_sql('dept_analyse',     conn, if_exists='replace', index=False)
reg_pivot.to_sql('region_analyse',    conn, if_exists='replace', index=False)
hist.to_sql('historique_national',    conn, if_exists='replace', index=False)
df_ref.to_sql('referentiel_oi',       conn, if_exists='replace', index=False)
op_national.to_sql('operateurs_nat',  conn, if_exists='replace', index=False)

# Créer la vue analytique directement dans SQLite
conn.execute("""
CREATE VIEW IF NOT EXISTS v_dept_kpis AS
SELECT
    t1.code_dept,
    t1.locaux_totaux,
    t1.raccordables                                                     AS raccordables_t1,
    t2.raccordables                                                     AS raccordables_t2,
    (t2.raccordables - t1.raccordables)                                 AS delta_t1_t2,
    ROUND((t2.raccordables - t1.raccordables)*100.0/MAX(t1.raccordables,1),2)  AS croissance_pct,
    ROUND(t2.raccordables*100.0/MAX(t1.locaux_totaux,1),2)             AS taux_couverture_pct,
    ROUND(t1.locaux_totaux - t2.raccordables,0)                        AS retard_objectif,
    CASE
        WHEN ROUND(t2.raccordables*100.0/MAX(t1.locaux_totaux,1),2) >= 95 THEN '🟢 ≥ 95%'
        WHEN ROUND(t2.raccordables*100.0/MAX(t1.locaux_totaux,1),2) >= 80 THEN '🟡 80–95%'
        WHEN ROUND(t2.raccordables*100.0/MAX(t1.locaux_totaux,1),2) >= 60 THEN '🟠 60–80%'
        ELSE '🔴 < 60%'
    END                                                                 AS statut_plan
FROM dept_deploiement t1
JOIN dept_deploiement t2 ON t1.code_dept = t2.code_dept
WHERE t1.trimestre='T1_2025' AND t2.trimestre='T2_2025'
ORDER BY taux_couverture_pct DESC
""")
conn.commit()
conn.close()

print(f"\n✅  Exports terminés dans {OUT_DIR}")
print(f"   → SQLite : {db_path}")
print(f"   → CSV    : 6 fichiers")
print(f"   → Tables : dept_deploiement, region_deploiement, dept_analyse, reg_analyse, historique_national, referentiel_oi, operateurs_nat")
print(f"   → Vue    : v_dept_kpis")
