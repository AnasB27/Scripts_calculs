import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as mplcm
import xlrd

# Distances géophones (mm) — configuration standard 13 capteurs
GEOPHONE_DISTANCES = [0, 30, 40, 50, 60, 75, 90, 105, 120, 150, 180, 210, 240]

# Niveaux d'effort standard (kN)
NIVEAUX_EFFORT = [250, 200, 150, 125, 100, 75]

# Colonnes déflexion dans la base normalisée
DEFLEXION_COLS = [f'd{i+1}' for i in range(13)]


def charger_excel_brut(xls_path):
    """
    Charge le fichier Excel brut STAC/Dynatest et retourne un dict de DataFrames
    structurés par feuille :
      - 'pesage'     : vérification du système de pesage dynamique
      - 'chaussee'   : essais sur chaussée souple (déflexions)
      - 'ancrages'   : ancrages profonds
    """
    wb = xlrd.open_workbook(xls_path)
    result = {}

    for sheet_name in wb.sheet_names():
        ws = wb.sheet_by_name(sheet_name)
        key = _detecter_cle_feuille(sheet_name)
        result[key] = _parser_feuille(ws, key)

    return result


def _detecter_cle_feuille(name):
    n = name.lower()
    if 'pesage' in n or 'pesag' in n:
        return 'pesage'
    if 'souple' in n or 'chaussee' in n or 'chaussée' in n or 'ec' in n:
        return 'chaussee'
    if 'ancrage' in n or 'profond' in n:
        return 'ancrages'
    return name


def _parser_feuille(ws, key):
    """Parse une feuille Excel en DataFrame structuré selon son type."""
    if key == 'chaussee':
        return _parser_chaussee_souple(ws)
    elif key in ('pesage', 'ancrages'):
        return _parser_pesage_ancrages(ws)
    else:
        rows = [ws.row_values(i) for i in range(ws.nrows)]
        return pd.DataFrame(rows)


def _parser_chaussee_souple(ws):
    """
    Parse la feuille 'EC chaussée souple'.
    Structure : colonnes fixes = [Zone, Point, Chainage, Niveau, Label_effort, Chute, Fmax, d1..d13]
    Les en-têtes de colonnes apparaissent à plusieurs reprises (en-tête de passage).
    Les colonnes Zone, Point, Chainage et Niveau ne sont renseignées qu'à la première chute de chaque groupe.
    """
    records = []
    passage_courant = None
    appareil = None

    # Valeurs "courantes" propagées entre les chutes d'un même groupe
    zone_cur = None
    point_cur = None
    chainage_cur = None
    niveau_cur = None
    label_cur = ''

    for i in range(ws.nrows):
        row = ws.row_values(i)

        # Détection de l'appareil (FWD/HWD)
        if str(row[1]).strip().lower().startswith("type d'appareil"):
            for cell in row:
                c = str(cell).strip().upper()
                if c in ('FWD', 'HWD'):
                    appareil = c
                    break

        # Détection du passage (ex : "Passage 1", "PASSAGE 1")
        for cell in row:
            s = str(cell).strip().upper()
            if s.startswith('PASSAGE'):
                try:
                    num = int(float(s.split()[-1]))
                    passage_courant = num
                except (ValueError, IndexError):
                    pass

        fmax_val = row[7] if len(row) > 7 else ''
        chute_val = row[6] if len(row) > 6 else ''

        try:
            fmax = float(fmax_val) if str(fmax_val).strip() else None
        except (ValueError, TypeError):
            fmax = None

        try:
            chute = int(float(chute_val)) if str(chute_val).strip() else None
        except (ValueError, TypeError):
            chute = None

        if fmax is not None and fmax > 0:
            # Mise à jour des valeurs de groupe si la ligne les renseigne
            zone_val = row[1]
            try:
                z = float(zone_val) if str(zone_val).strip() else None
                if z is not None:
                    zone_cur = z
            except (ValueError, TypeError):
                pass

            pt_val = str(row[2]).strip() if len(row) > 2 else ''
            if pt_val:
                point_cur = pt_val

            try:
                ch = float(row[3]) if str(row[3]).strip() else None
                if ch is not None:
                    chainage_cur = ch
            except (ValueError, TypeError):
                pass

            try:
                niv = int(float(row[4])) if str(row[4]).strip() else None
                if niv is not None:
                    niveau_cur = niv
            except (ValueError, TypeError):
                pass

            lbl = str(row[5]).strip() if len(row) > 5 else ''
            if lbl:
                label_cur = lbl

            # Déflexions d1..d13
            deflexions = {}
            for k, col_idx in enumerate(range(8, 21)):
                if col_idx < len(row):
                    try:
                        val = float(row[col_idx]) if str(row[col_idx]).strip() else np.nan
                    except (ValueError, TypeError):
                        val = np.nan
                    deflexions[f'd{k+1}'] = val

            record = {
                'appareil': appareil,
                'passage': passage_courant,
                'zone': zone_cur,
                'point': point_cur,
                'chainage': chainage_cur,
                'niveau_effort': niveau_cur,
                'label_effort': label_cur,
                'Fmax_kN': fmax,
                'chute': chute,
            }
            record.update(deflexions)
            records.append(record)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _parser_pesage_ancrages(ws):
    """
    Parse les feuilles pesage / ancrages profonds.
    Structure : blocs de 3 passages × 3 niveaux d'effort, colonnes = [Passage, Essai, Chute, Fmax].
    Les colonnes Passage et Essai ne sont renseignées que sur la chute 1 ; les valeurs sont
    propagées aux chutes 2 et 3 (même principe que zone/point dans _parser_chaussee_souple).
    """
    records = []
    bloc_effort = None
    # Propagation de passage et essai par colonne de bloc (offsets 1, 6, 11)
    passage_cur = [None, None, None]
    essai_cur   = [None, None, None]

    for i in range(ws.nrows):
        row = ws.row_values(i)

        # Détection du niveau d'effort courant (en-têtes de bloc)
        for cell in row:
            s = str(cell).strip()
            if "niveau d'effort" in s.lower() or "niveau d effort" in s.lower():
                m = re.search(r'F\s*=\s*(\d+)', s)
                if m:
                    bloc_effort = int(m.group(1))

        # Chercher les colonnes "Passage, Nom de l'essai, Chutes, Forces max"
        # Ces colonnes apparaissent en triple (3 blocs côte à côte)
        # Colonnes 1,2,3,4 | 6,7,8,9 | 11,12,13,14
        for col_idx, offset in enumerate([1, 6, 11]):
            if len(row) > offset + 3:
                passage_val = row[offset]
                essai_val   = row[offset + 1]
                chute_val   = row[offset + 2]
                fmax_val    = row[offset + 3]

                try:
                    p = int(float(passage_val)) if str(passage_val).strip() else None
                    if p is not None:
                        passage_cur[col_idx] = p
                except (ValueError, TypeError):
                    pass

                try:
                    e = float(essai_val) if str(essai_val).strip() else None
                    if e is not None:
                        essai_cur[col_idx] = e
                except (ValueError, TypeError):
                    pass

                try:
                    chute = int(float(chute_val)) if str(chute_val).strip() else None
                    fmax  = float(fmax_val)        if str(fmax_val).strip()  else None
                except (ValueError, TypeError):
                    chute = fmax = None

                if passage_cur[col_idx] is not None and chute is not None and fmax is not None and fmax > 0:
                    records.append({
                        'passage':         passage_cur[col_idx],
                        'essai':           essai_cur[col_idx],
                        'chute':           chute,
                        'Fmax_kN':         fmax,
                        'effort_cible_kN': bloc_effort,
                    })

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def charger_csv_normalise(csv_path):
    """Charge la base de données normalisée (CSV) issue du formatage."""
    try:
        df = pd.read_csv(csv_path, sep=None, engine='python', encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, sep=None, engine='python', encoding='latin1')
    return df


def sauvegarder_csv(df, csv_path):
    df.to_csv(csv_path, index=False)


# ── Analyses statistiques ──────────────────────────────────────────────────────

def calculer_repetabilite(df, col_deflexion='d1', groupby=None):
    """
    Calcule la répétabilité (écart-type) des déflexions pour chaque groupe
    (participant × point × niveau d'effort × passage par défaut).
    """
    if groupby is None:
        groupby = ['participant', 'point', 'niveau_effort', 'passage']
    cols_present = [c for c in groupby if c in df.columns]
    if col_deflexion not in df.columns:
        raise ValueError(f"Colonne '{col_deflexion}' absente du DataFrame.")
    return df.groupby(cols_present)[col_deflexion].agg(['mean', 'std', 'count']).reset_index()


def calculer_reproductibilite(df, col_deflexion='d1', groupby=None):
    """
    Calcule la reproductibilité (dispersion entre passages) pour chaque groupe
    (participant × point × niveau d'effort par défaut).
    """
    if groupby is None:
        groupby = ['participant', 'point', 'niveau_effort']
    cols_present = [c for c in groupby if c in df.columns]
    if col_deflexion not in df.columns:
        raise ValueError(f"Colonne '{col_deflexion}' absente du DataFrame.")
    return df.groupby(cols_present)[col_deflexion].agg(['mean', 'std', 'min', 'max', 'count']).reset_index()


def calculer_linearite(df, col_deflexion='d1'):
    """
    Calcule la linéarité : rapport déflexion / Fmax pour chaque mesure.
    Retourne le DataFrame enrichi d'une colonne 'ratio_d_F'.
    """
    df = df.copy()
    if 'Fmax_kN' in df.columns and col_deflexion in df.columns:
        df['ratio_d_F'] = df[col_deflexion] / df['Fmax_kN']
    return df


def calculer_bouclage(df, col_deflexion='d1'):
    """
    Étudie le bouclage : compare les mesures au niveau d'effort 250 kN
    entre le début et la fin de la séquence (niveau 1 et niveau 7).
    """
    if 'niveau_effort' not in df.columns:
        return pd.DataFrame()
    n1 = df[df['niveau_effort'] == 1].copy()
    n7 = df[df['niveau_effort'] == 7].copy()
    if n1.empty or n7.empty:
        return pd.DataFrame()
    groupby = [c for c in ['participant', 'point', 'passage'] if c in df.columns]
    m1 = n1.groupby(groupby)[col_deflexion].mean().reset_index().rename(columns={col_deflexion: 'd_debut'})
    m7 = n7.groupby(groupby)[col_deflexion].mean().reset_index().rename(columns={col_deflexion: 'd_fin'})
    merged = m1.merge(m7, on=groupby, how='inner')
    merged['delta_bouclage'] = merged['d_fin'] - merged['d_debut']
    merged['bouclage_pct'] = 100 * merged['delta_bouclage'] / merged['d_debut']
    return merged


def calculer_chute_representative(df, col_deflexion='d1'):
    """
    Identifie la chute représentative : chute dont la déflexion est la plus proche
    de la moyenne sur les 3 chutes, par groupe.
    """
    groupby = [c for c in ['participant', 'point', 'niveau_effort', 'passage'] if c in df.columns]
    if col_deflexion not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    moy = df.groupby(groupby)[col_deflexion].transform('mean')
    df['ecart_moy'] = abs(df[col_deflexion] - moy)
    idx = df.groupby(groupby)['ecart_moy'].idxmin()
    return df.loc[idx].drop(columns=['ecart_moy']).reset_index(drop=True)


# ── Vérification pesage ────────────────────────────────────────────────────────

def analyser_pesage(df_pesage):
    """
    Analyse la répétabilité et la précision du système de pesage dynamique.
    Retourne un résumé par niveau d'effort.
    """
    if df_pesage.empty or 'Fmax_kN' not in df_pesage.columns:
        return pd.DataFrame()
    groupby = [c for c in ['effort_cible_kN', 'passage'] if c in df_pesage.columns]
    return df_pesage.groupby(groupby)['Fmax_kN'].agg(
        moyenne='mean', ecart_type='std', minimum='min', maximum='max', nb_chutes='count'
    ).reset_index()


# ── Tracés ────────────────────────────────────────────────────────────────────

def tracer_bassins_deflexion(df, point=None, passage=None, niveau=None,
                              appareil=None, participant=None, ax=None, titre=None):
    """
    Trace le bassin de déflexion (d1..d13 en fonction de la distance au centre).
    Filtres optionnels : point, passage, niveau d'effort, participant.
    """
    df_f = df.copy()
    if appareil is not None and 'appareil' in df_f.columns:
        df_f = df_f[df_f['appareil'] == appareil]
    if participant is not None and 'participant' in df_f.columns:
        df_f = df_f[df_f['participant'] == participant]
    if point is not None and 'point' in df_f.columns:
        df_f = df_f[df_f['point'] == point]
    if passage is not None and 'passage' in df_f.columns:
        df_f = df_f[df_f['passage'] == passage]
    if niveau is not None and 'niveau_effort' in df_f.columns:
        df_f = df_f[df_f['niveau_effort'] == niveau]

    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 6))

    for _, row in df_f.iterrows():
        vals = [row.get(f'd{k+1}', np.nan) for k in range(13)]
        label = f"Chute {int(row['chute'])}" if 'chute' in row and not pd.isna(row['chute']) else ''
        ax.plot(GEOPHONE_DISTANCES, vals, marker='o', markersize=4, label=label)

    ax.set_xlabel('Distance au centre de charge (cm)')
    ax.set_ylabel('Déflexion (µm)')
    t = titre or f"Bassin de déflexion — {point or ''} Passage {passage or ''} N{niveau or ''}"
    ax.set_title(t)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.4)
    ax.invert_yaxis()
    if show:
        plt.tight_layout()
        plt.show()


def tracer_histogramme_deflexion(df, col='d1', bins=10, ax=None, titre=None):
    """Histogramme de la distribution de la déflexion centrale (d1)."""
    data = df[col].dropna()
    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(data, bins=bins, color='steelblue', edgecolor='black', alpha=0.7)
    ax.set_xlabel(f'Déflexion {col} (µm)')
    ax.set_ylabel('Effectif')
    ax.set_title(titre or f'Distribution de {col}')
    ax.grid(axis='y', alpha=0.5)
    if show:
        plt.tight_layout()
        plt.show()


def tracer_boxplot_repetabilite(df, col='d1', groupby='point', ax=None):
    """Boxplot de la répétabilité par groupe (point par défaut)."""
    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 6))
    if groupby not in df.columns or col not in df.columns:
        return
    groupes = df[groupby].dropna().unique()
    data = [df[df[groupby] == g][col].dropna().values for g in groupes]
    ax.boxplot(data, labels=[str(g) for g in groupes])
    ax.set_xlabel(groupby)
    ax.set_ylabel(f'{col} (µm)')
    ax.set_title(f'Répétabilité — {col} par {groupby}')
    ax.grid(axis='y', alpha=0.4)
    if show:
        plt.tight_layout()
        plt.show()


def tracer_linearite(df, col='d1', ax=None, appareil=None, point=None, participant=None):
    """
    Trace la déflexion en fonction de la force (linéarité).
    Un point par chute, couleurs par niveau d'effort.
    """
    df_f = df.copy()
    if appareil is not None and 'appareil' in df_f.columns:
        df_f = df_f[df_f['appareil'] == appareil]
    if participant is not None and 'participant' in df_f.columns:
        df_f = df_f[df_f['participant'] == participant]
    if point is not None and 'point' in df_f.columns:
        df_f = df_f[df_f['point'] == point]

    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 6))

    niveaux = sorted(df_f['niveau_effort'].dropna().unique()) if 'niveau_effort' in df_f.columns else [None]
    cmap = mplcm.get_cmap('tab10', len(niveaux))
    for idx, niv in enumerate(niveaux):
        sub = df_f[df_f['niveau_effort'] == niv] if niv is not None else df_f
        ax.scatter(sub['Fmax_kN'], sub[col], color=cmap(idx),
                   label=f'N{niv}', alpha=0.7, s=40)

    ax.set_xlabel('Force max (kN)')
    ax.set_ylabel(f'{col} (µm)')
    ax.set_title(f'Linéarité — {col} vs Fmax ({point or ""})')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.4)
    if show:
        plt.tight_layout()
        plt.show()


def tracer_bouclage(df_bouclage, ax=None):
    """Bar chart du delta de bouclage (%) par point."""
    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))
    if df_bouclage.empty or 'bouclage_pct' not in df_bouclage.columns:
        return
    labels = df_bouclage['point'].astype(str) if 'point' in df_bouclage.columns else df_bouclage.index.astype(str)
    ax.bar(labels, df_bouclage['bouclage_pct'], color='coral', edgecolor='black')
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_xlabel("Point d'essai")
    ax.set_ylabel('Δ bouclage (%)')
    ax.set_title("Étude de bouclage")
    ax.grid(axis='y', alpha=0.4)
    if show:
        plt.tight_layout()
        plt.show()


def tracer_pesage(df_pesage_analyse, ax=None):
    """Tracé erreur relative (%) par niveau d'effort cible."""
    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))
    if df_pesage_analyse.empty:
        return
    df_p = df_pesage_analyse.copy()
    if 'effort_cible_kN' in df_p.columns:
        df_p['erreur_pct'] = 100 * (df_p['moyenne'] - df_p['effort_cible_kN']) / df_p['effort_cible_kN']
        moy_err = df_p.groupby('effort_cible_kN')['erreur_pct'].mean()
        ax.bar([str(int(n)) for n in moy_err.index], moy_err.values, color='steelblue', edgecolor='black')
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_xlabel('Niveau cible (kN)')
        ax.set_ylabel('Erreur relative (%)')
        ax.set_title("Vérification du système de pesage")
        ax.grid(axis='y', alpha=0.4)
    if show:
        plt.tight_layout()
        plt.show()


# ── Coefficients de variation (répétabilité) ──────────────────────────────────

def calculer_cv_repetabilite(df, col_deflexions=None):
    """
    Calcule le coefficient de variation (CV) des 3 chutes par groupe
    (participant × point × niveau_effort × passage) pour chaque déflexion.
    Retourne un DataFrame avec les CV moyens par participant et par géophone.
    Correspond aux Figures 2-4 à 2-10 du rapport EC 2022.
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]
    groupby = [c for c in ['participant', 'point', 'niveau_effort', 'passage'] if c in df.columns]

    # CV pour chaque groupe (3 chutes)
    def cv(x):
        m = x.mean()
        return (x.std() / m * 100) if m != 0 else 0.0

    cvs = df.groupby(groupby)[col_deflexions].agg(cv).reset_index()
    return cvs


def calculer_cv_moyen_par_appareil(df, col_deflexions=None):
    """
    Moyenne des CV sur l'ensemble des essais (tous points × passages) par participant.
    Figure 2-5 / 2-6 du rapport : un bar chart par participant, CV moyen tous géophones confondus.
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]
    cvs = calculer_cv_repetabilite(df, col_deflexions)
    if 'participant' in cvs.columns:
        return cvs.groupby('participant')[col_deflexions].mean().reset_index()
    return cvs[col_deflexions].mean().to_frame().T


def calculer_cv_moyen_par_geophone(df, col_deflexions=None):
    """
    Moyenne générale par géophone, tous appareils confondus.
    Figure 2-7 / 2-10 du rapport.
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]
    cvs = calculer_cv_repetabilite(df, col_deflexions)
    return cvs[col_deflexions].mean()


# ── Critère de linéarité (R²) ─────────────────────────────────────────────────

def calculer_critere_linearite(df, col_deflexions=None):
    """
    Calcule le coefficient de détermination R² (régression linéaire déflexion vs Fmax)
    pour chaque groupe (participant × point × passage) et chaque géophone.
    Correspond aux Figures 2-10, 2-11 et Tableaux C.1–C.4 du rapport.

    Retourne un DataFrame avec colonnes : [participant, point, passage, d1_R2, d2_R2, ..., d9_R2, mean_R2]
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]

    groupby = [c for c in ['participant', 'point', 'passage'] if c in df.columns]
    results = []

    for name, grp in df.groupby(groupby):
        if len(grp) < 3:
            continue
        if 'Fmax_kN' not in grp.columns:
            continue
        row_data = dict(zip(groupby, name if isinstance(name, tuple) else [name]))
        r2_vals = []
        for col in col_deflexions:
            if col not in grp.columns:
                continue
            sub = grp[['Fmax_kN', col]].dropna()
            if len(sub) < 3:
                row_data[f'{col}_R2'] = np.nan
                continue
            x = sub['Fmax_kN'].values
            y = sub[col].values
            # R² par régression linéaire
            n = len(x)
            sx = x.sum(); sy = y.sum()
            sxx = (x*x).sum(); sxy = (x*y).sum(); syy = (y*y).sum()
            denom = n*syy - sy**2
            if denom == 0:
                r2 = np.nan
            else:
                r2 = (n*sxy - sx*sy)**2 / ((n*sxx - sx**2) * denom)
            row_data[f'{col}_R2'] = r2
            if not np.isnan(r2):
                r2_vals.append(r2)
        row_data['mean_R2'] = np.mean(r2_vals) if r2_vals else np.nan
        results.append(row_data)

    return pd.DataFrame(results) if results else pd.DataFrame()


# ── Bouclage détaillé (comparaison bassins N1/N7) ─────────────────────────────

def calculer_bouclage_detaille(df, col_deflexions=None):
    """
    Compare les bassins de déflexion normalisés (d/F) entre le premier niveau (N1=250kN)
    et le dernier (N7=bouclage) pour chaque appareil × point × passage.
    Retourne un DataFrame avec les écarts relatifs (%) par géophone.
    Correspond aux Figures 2-12, 2-13, 2-14, 2-15 du rapport.
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]
    if 'niveau_effort' not in df.columns:
        return pd.DataFrame()

    groupby = [c for c in ['participant', 'point', 'passage'] if c in df.columns]

    # Normaliser par Fmax
    df_norm = df.copy()
    for col in col_deflexions:
        if col in df_norm.columns and 'Fmax_kN' in df_norm.columns:
            df_norm[col + '_norm'] = df_norm[col] / df_norm['Fmax_kN']

    norm_cols = [c + '_norm' for c in col_deflexions if c + '_norm' in df_norm.columns]

    n1 = df_norm[df_norm['niveau_effort'] == 1]
    n7 = df_norm[df_norm['niveau_effort'] == 7]

    if n1.empty or n7.empty:
        return pd.DataFrame()

    # Moyenne des chutes représentatives par groupe
    m1 = n1.groupby(groupby)[norm_cols].mean().reset_index()
    m7 = n7.groupby(groupby)[norm_cols].mean().reset_index()

    merged = m1.merge(m7, on=groupby, suffixes=('_debut', '_fin'))

    # Calculer les écarts relatifs
    for col in norm_cols:
        col_base = col.replace('_norm', '')
        debut_col = col + '_debut'
        fin_col = col + '_fin'
        if debut_col in merged.columns and fin_col in merged.columns:
            merged[col_base + '_ecart_pct'] = 100 * (merged[fin_col] - merged[debut_col]) / merged[debut_col].replace(0, np.nan)

    return merged


# ── Dispersions comparatives inter-appareils et inter-points ─────────────────

def calculer_dispersion_inter_appareils(df, col_deflexions=None, niveau_effort=None):
    """
    Calcule les coefficients de variation inter-participants pour chaque point et géophone.
    Correspond aux Tableaux 2-13, 2-14 et Figure 2-22 du rapport.

    Pour chaque point d'essai :
      - normalise les déflexions par l'effort (d/F)
      - calcule la moyenne et le CV sur tous les participants
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]

    df_work = df.copy()
    if niveau_effort is not None and 'niveau_effort' in df_work.columns:
        df_work = df_work[df_work['niveau_effort'] == niveau_effort]

    # Normaliser d/F
    norm_cols = []
    for col in col_deflexions:
        if col in df_work.columns and 'Fmax_kN' in df_work.columns:
            nc = col + '_norm'
            df_work[nc] = df_work[col] / df_work['Fmax_kN']
            norm_cols.append(nc)

    if not norm_cols:
        return pd.DataFrame()

    # Grouper par participant × point, puis calculer la moyenne par participant
    groupby_participant = [c for c in ['participant', 'point'] if c in df_work.columns]
    moy_par_app = df_work.groupby(groupby_participant)[norm_cols].mean().reset_index()

    # CV inter-participants par point
    results = []
    if 'point' in moy_par_app.columns:
        for pt, grp in moy_par_app.groupby('point'):
            row = {'point': pt}
            for nc in norm_cols:
                m = grp[nc].mean()
                s = grp[nc].std()
                row[nc.replace('_norm', '_CV_pct')] = (s / m * 100) if m != 0 else 0.0
                row[nc.replace('_norm', '_moy')] = m
                row[nc.replace('_norm', '_std')] = s
            results.append(row)

    return pd.DataFrame(results) if results else pd.DataFrame()


def calculer_dispersion_inter_points(df, col_deflexions=None, niveau_effort=None):
    """
    Calcule les coefficients de variation inter-points (Tableau 2-15, Figure 2-23).
    Pour chaque géophone : calcule la moyenne sur tous les appareils pour chaque point,
    puis le CV de ces moyennes entre les différents points.
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]

    df_work = df.copy()
    if niveau_effort is not None and 'niveau_effort' in df_work.columns:
        df_work = df_work[df_work['niveau_effort'] == niveau_effort]

    # Normaliser d/F
    norm_cols = []
    for col in col_deflexions:
        if col in df_work.columns and 'Fmax_kN' in df_work.columns:
            nc = col + '_norm'
            df_work[nc] = df_work[col] / df_work['Fmax_kN']
            norm_cols.append(nc)

    if not norm_cols or 'point' not in df_work.columns:
        return pd.DataFrame()

    # Moyenne par point (tous appareils confondus)
    moy_par_point = df_work.groupby('point')[norm_cols].mean()

    # CV entre les points
    result = {}
    for nc in norm_cols:
        col_base = nc.replace('_norm', '')
        vals = moy_par_point[nc]
        m = vals.mean()
        s = vals.std()
        result[col_base + '_moy_points'] = m
        result[col_base + '_std_points'] = s
        result[col_base + '_CV_points_pct'] = (s / m * 100) if m != 0 else 0.0

    return pd.DataFrame([result])


# ── Coefficients de correction d'effort ───────────────────────────────────────

def calculer_coefficients_correction(df_pesage):
    """
    Calcule les coefficients de correction α tels que F_balance = α × F_HWD.
    α = F_pesage_moyen / F_HWD_moyen par participant.
    Correspond au Tableau 1-1 du rapport.

    df_pesage doit contenir les colonnes 'Fmax_kN' (force F/HWD) et 'effort_cible_kN' (force pesage).
    """
    if df_pesage.empty or 'effort_cible_kN' not in df_pesage.columns or 'Fmax_kN' not in df_pesage.columns:
        return pd.DataFrame()

    if 'participant' in df_pesage.columns:
        grp = df_pesage.groupby('participant')
        result = grp.apply(lambda g: g['effort_cible_kN'].mean() / g['Fmax_kN'].mean()).reset_index()
        result.columns = ['participant', 'alpha']
    else:
        alpha = df_pesage['effort_cible_kN'].mean() / df_pesage['Fmax_kN'].mean()
        result = pd.DataFrame([{'participant': 'global', 'alpha': alpha}])

    return result


def appliquer_correction_effort(df_chaussee, coefficients):
    """
    Applique les coefficients de correction sur les déflexions normalisées.
    d_corr = d / α (car F_réel = α × F_HWD, donc d_norm_corr = d / F_réel = d / (α × F_HWD))

    coefficients : DataFrame avec colonnes ['participant', 'alpha']
    Retourne le df avec les déflexions corrigées (colonnes d1_corr, d2_corr, ...).
    """
    df = df_chaussee.copy()
    col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]

    if 'participant' not in df.columns:
        return df

    coeff_dict = dict(zip(coefficients['participant'], coefficients['alpha']))

    for col in col_deflexions:
        corr_col = col + '_corr'
        df[corr_col] = df.apply(
            lambda row: row[col] / coeff_dict.get(row['participant'], 1.0) if pd.notna(row.get(col)) else np.nan,
            axis=1
        )

    return df


# ── Tracés supplémentaires ────────────────────────────────────────────────────

def tracer_cv_par_appareil(df_cv, col_deflexions=None, ax=None, titre=None):
    """
    Bar chart des CV moyens par participant (Figure 2-5 / 2-6 du rapport).
    df_cv provient de calculer_cv_moyen_par_appareil().
    """
    if col_deflexions is None:
        col_deflexions = [c for c in DEFLEXION_COLS if c in df_cv.columns]

    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))

    if 'participant' in df_cv.columns:
        participants = df_cv['participant'].values
        vals = df_cv[col_deflexions].mean(axis=1).values
        ax.bar([str(a) for a in participants], vals, color='steelblue', edgecolor='black', alpha=0.8)
        ax.set_xlabel('Participant')
    else:
        vals = df_cv[col_deflexions].values.flatten()
        ax.bar(col_deflexions, vals, color='steelblue', edgecolor='black', alpha=0.8)
        ax.set_xlabel('Géophone')

    ax.set_ylabel('CV moyen (%)')
    ax.set_title(titre or "Coefficients de variation moyens par participant")
    ax.grid(axis='y', alpha=0.4)
    if show:
        plt.tight_layout(); plt.show()


def tracer_cv_par_geophone(cv_serie, col_deflexions=None, niveaux=None, ax=None, titre=None):
    """
    Bar chart des CV moyens par géophone (Figure 2-7 / 2-10 du rapport).
    cv_serie : Series ou dict {géophone: CV_moyen}.
    niveaux : optionnel, dict {label: Series} pour superposer plusieurs niveaux.
    """
    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))

    if niveaux is not None:
        x = np.arange(len(list(niveaux.values())[0]))
        width = 0.8 / len(niveaux)
        colors = ['steelblue', 'coral', 'seagreen', 'mediumpurple', 'orange']
        for i, (label, serie) in enumerate(niveaux.items()):
            vals = serie.values if hasattr(serie, 'values') else list(serie.values())
            keys = serie.index.tolist() if hasattr(serie, 'index') else list(serie.keys())
            ax.bar(x + i*width, vals, width, label=label, color=colors[i % len(colors)], edgecolor='black', alpha=0.8)
        ax.set_xticks(x + width*(len(niveaux)-1)/2)
        ax.set_xticklabels(keys, fontsize=9)
        ax.legend(fontsize=9)
    else:
        if hasattr(cv_serie, 'values'):
            ax.bar(cv_serie.index, cv_serie.values, color='steelblue', edgecolor='black', alpha=0.8)
        else:
            ax.bar(list(cv_serie.keys()), list(cv_serie.values()), color='steelblue', edgecolor='black', alpha=0.8)

    ax.set_xlabel('Géophone')
    ax.set_ylabel('CV moyen (%)')
    ax.set_title(titre or "Coefficient de variation moyen par géophone")
    ax.grid(axis='y', alpha=0.4)
    if show:
        plt.tight_layout(); plt.show()


def tracer_bouclage_detaille(df_bouclage_detail, col_deflexions=None, ax=None, titre=None):
    """
    Trace les écarts moyens (%) entre début et fin de cycle par géophone (Figure 2-12/2-13).
    Si plusieurs appareils sont présents, trace une courbe par appareil.
    """
    if col_deflexions is None:
        col_deflexions = DEFLEXION_COLS

    ecart_cols = [c + '_ecart_pct' for c in col_deflexions if c + '_ecart_pct' in df_bouclage_detail.columns]
    if not ecart_cols:
        return

    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))

    distances = GEOPHONE_DISTANCES[:len(ecart_cols)]

    if 'participant' in df_bouclage_detail.columns:
        cmap = mplcm.get_cmap('tab10', df_bouclage_detail['participant'].nunique())
        for i, (app, grp) in enumerate(df_bouclage_detail.groupby('participant')):
            vals = grp[ecart_cols].mean().values
            ax.plot(distances, vals, marker='o', markersize=5, color=cmap(i), label=str(app))
        ax.legend(fontsize=9)
    else:
        vals = df_bouclage_detail[ecart_cols].mean().values
        ax.plot(distances, vals, marker='o', markersize=5, color='coral')

    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_xlabel('Distance au centre de chargement (cm)')
    ax.set_ylabel('Écart moyen (%)')
    ax.set_title(titre or "Étude de bouclage — Écarts entre début et fin de cycle")
    ax.grid(True, alpha=0.4)
    if show:
        plt.tight_layout(); plt.show()


def tracer_r2_linearite(df_r2, col_deflexions=None, ax=None, titre=None):
    """
    Trace le coefficient R² en fonction du géophone pour chaque appareil (Figure 2-10/2-11).
    df_r2 provient de calculer_critere_linearite().
    """
    if col_deflexions is None:
        col_deflexions = DEFLEXION_COLS

    r2_cols = [f'{c}_R2' for c in col_deflexions if f'{c}_R2' in df_r2.columns]
    if not r2_cols:
        return

    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))

    geophone_labels = [c.replace('_R2', '') for c in r2_cols]

    if 'participant' in df_r2.columns:
        cmap = mplcm.get_cmap('tab10', df_r2['participant'].nunique())
        for i, (app, grp) in enumerate(df_r2.groupby('participant')):
            vals = grp[r2_cols].mean().values
            ax.plot(geophone_labels, vals, marker='o', markersize=5, color=cmap(i), label=str(app))
        ax.legend(fontsize=9)
    else:
        vals = df_r2[r2_cols].mean().values
        ax.plot(geophone_labels, vals, marker='o', markersize=5, color='steelblue')

    # Lignes de seuil
    ax.axhline(0.987, color='red', linestyle='--', linewidth=1, label='Seuil HWD (0.987)')
    ax.axhline(0.973, color='orange', linestyle='--', linewidth=1, label='Seuil FWD (0.973)')

    ax.set_xlabel('Géophone')
    ax.set_ylabel('R²')
    ax.set_title(titre or "Critère de linéarité — Coefficient de détermination R²")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.4)
    ax.set_ylim(0.95, 1.005)
    if show:
        plt.tight_layout(); plt.show()


def tracer_dispersion_comparative(df_inter_app, df_inter_pts, col_deflexions=None, ax=None, titre=None):
    """
    Figure 2-23 du rapport : superpose dispersion inter-appareils et inter-points en fonction
    de la distance au centre de chargement.
    """
    if col_deflexions is None:
        col_deflexions = DEFLEXION_COLS

    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 5))

    cv_app_cols = [c + '_CV_pct' for c in col_deflexions if c + '_CV_pct' in df_inter_app.columns]
    cv_pts_cols = [c + '_CV_points_pct' for c in col_deflexions if c + '_CV_points_pct' in df_inter_pts.columns]

    n = min(len(cv_app_cols), len(cv_pts_cols), len(GEOPHONE_DISTANCES))
    distances = GEOPHONE_DISTANCES[:n]

    if cv_app_cols:
        # Moyenne sur les points
        vals_app = df_inter_app[cv_app_cols[:n]].mean().values
        ax.plot(distances, vals_app, marker='s', markersize=6, color='steelblue',
                linewidth=2, label='Dispersion entre appareils')

    if cv_pts_cols:
        vals_pts = df_inter_pts[cv_pts_cols[:n]].values.flatten()[:n]
        ax.plot(distances, vals_pts, marker='^', markersize=6, color='coral',
                linewidth=2, label='Dispersion entre points')

    ax.set_xlabel('Distance au centre de chargement (cm)')
    ax.set_ylabel('Coefficient de variation (%)')
    ax.set_title(titre or "Comparaison des dispersions inter-appareils vs inter-points")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.4)
    if show:
        plt.tight_layout(); plt.show()


def tracer_ecart_pesage_detail(df_pesage, ax=None, titre=None):
    """
    Figure 1-3 du rapport : F_pesage vs F_HWD, un point par chute, couleur par appareil.
    Figure 1-4 : Écarts relatifs moyens par niveau d'effort (par appareil).
    """
    show = ax is None
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 6))

    if df_pesage.empty or 'effort_cible_kN' not in df_pesage.columns or 'Fmax_kN' not in df_pesage.columns:
        return

    # Écart relatif par niveau pour chaque appareil
    df = df_pesage.copy()
    df['ecart_rel'] = 100 * (df['Fmax_kN'] - df['effort_cible_kN']) / df['effort_cible_kN']

    if 'participant' in df.columns:
        cmap = mplcm.get_cmap('tab10', df['participant'].nunique())
        for i, (app, grp) in enumerate(df.groupby('participant')):
            moy = grp.groupby('effort_cible_kN')['ecart_rel'].mean()
            ax.plot(moy.index, moy.values, marker='o', markersize=6, color=cmap(i), label=str(app))
    else:
        moy = df.groupby('effort_cible_kN')['ecart_rel'].mean()
        ax.plot(moy.index, moy.values, marker='o', markersize=6, color='steelblue')

    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_xlabel('F pesage moyen (kN)')
    ax.set_ylabel('Écart relatif moyen (%)')
    ax.set_title(titre or "Écarts relatifs moyens par rapport au pesage dynamique")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.4)
    if show:
        plt.tight_layout(); plt.show()
