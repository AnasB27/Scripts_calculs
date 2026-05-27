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
    (point × niveau d'effort × passage par défaut).
    """
    if groupby is None:
        groupby = ['appareil', 'point', 'niveau_effort', 'passage']
    cols_present = [c for c in groupby if c in df.columns]
    if col_deflexion not in df.columns:
        raise ValueError(f"Colonne '{col_deflexion}' absente du DataFrame.")
    return df.groupby(cols_present)[col_deflexion].agg(['mean', 'std', 'count']).reset_index()


def calculer_reproductibilite(df, col_deflexion='d1', groupby=None):
    """
    Calcule la reproductibilité (dispersion entre passages) pour chaque groupe
    (point × niveau d'effort par défaut).
    """
    if groupby is None:
        groupby = ['appareil', 'point', 'niveau_effort']
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
    groupby = [c for c in ['appareil', 'point', 'passage'] if c in df.columns]
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
    groupby = [c for c in ['appareil', 'point', 'niveau_effort', 'passage'] if c in df.columns]
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
                              appareil=None, ax=None, titre=None):
    """
    Trace le bassin de déflexion (d1..d13 en fonction de la distance au centre).
    Filtres optionnels : point, passage, niveau d'effort, appareil.
    """
    df_f = df.copy()
    if appareil is not None:
        df_f = df_f[df_f['appareil'] == appareil]
    if point is not None:
        df_f = df_f[df_f['point'] == point]
    if passage is not None:
        df_f = df_f[df_f['passage'] == passage]
    if niveau is not None:
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


def tracer_linearite(df, col='d1', ax=None, appareil=None, point=None):
    """
    Trace la déflexion en fonction de la force (linéarité).
    Un point par chute, couleurs par niveau d'effort.
    """
    df_f = df.copy()
    if appareil is not None and 'appareil' in df_f.columns:
        df_f = df_f[df_f['appareil'] == appareil]
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
    ax.set_title(f'Linéarité — {col} vs Fmax ({appareil or ""} {point or ""})')
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
