"""Onglet d'analyse des efforts corrigés (section 3 du rapport EC 2022)."""
import numpy as np
import matplotlib.cm as mplcm

from PyQt5.QtWidgets import (
    QLabel, QComboBox, QMessageBox,
    QWidget, QVBoxLayout, QSplitter, QTableWidget, QTabWidget, QSizePolicy
)
from PyQt5.QtCore import Qt

from Calcul.Calculs_portance import (
    calculer_coefficients_correction, appliquer_correction_effort,
    calculer_dispersion_inter_appareils, tracer_dispersion_comparative,
    calculer_dispersion_inter_points, DEFLEXION_COLS, GEOPHONE_DISTANCES
)
from Interfaces.onglet_base import OngletBase
from Interfaces.widgets_communs import (
    bouton, NavigationCanvas, remplir_tableau, peupler_combo, appliquer_filtre_df,
    CheckableComboBox
)


class EffortsCorrigesTab(OngletBase):
    titre_onglet = "Efforts corrigés"
    desc_onglet = ("Applique les coefficients de correction d'effort (Tableau 1-1) puis compare "
                   "les déflexions corrigées entre appareils et entre points d'essai "
                   "(Section 3 du rapport EC 2022).")

    def __init__(self):
        self._coefficients = None
        super().__init__()

    def _build_controls(self):
        self.combo_participant = CheckableComboBox()
        self.combo_participant.setMinimumWidth(160)
        self.combo_niveau = QComboBox()
        self.combo_niveau.addItem("Tous")
        btn_calc = bouton("Calculer corrections")
        btn_calc.clicked.connect(self._calculer)
        btn_comp = bouton("Comparer (brut vs corrigé)")
        btn_comp.clicked.connect(self._comparer)
        return self._ctrl_row(
            QLabel("Participant :"), self.combo_participant,
            QLabel("Niveau d'effort :"), self.combo_niveau,
            None, btn_calc, btn_comp
        )

    def _build_content(self) -> QWidget:
        tabs = QTabWidget()
        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        def _make_sub():
            w = QWidget()
            lv = QVBoxLayout(w)
            lv.setContentsMargins(0, 4, 0, 0)
            lv.setSpacing(0)
            sp = QSplitter(Qt.Horizontal)
            sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            tbl = QTableWidget()
            tbl.setMinimumWidth(300)
            sp.addWidget(tbl)
            cv = NavigationCanvas(figsize=(7, 4))
            wc = QWidget()
            vb = QVBoxLayout(wc)
            vb.setContentsMargins(0, 0, 0, 0)
            vb.setSpacing(0)
            vb.addWidget(cv.get_toolbar())
            vb.addWidget(cv, stretch=1)
            sp.addWidget(wc)
            sp.setSizes([380, 520])
            sp.setStretchFactor(0, 0)
            sp.setStretchFactor(1, 1)
            lv.addWidget(sp, stretch=1)
            return w, tbl, cv

        w1, self.table_coeff, self.canvas_coeff = _make_sub()
        w2, self.table_comp, self.canvas_comp = _make_sub()
        w3, self.table_bassins, self.canvas_bassins = _make_sub()

        tabs.addTab(w1, "Coefficients α (Tab. 1-1)")
        tabs.addTab(w2, "Dispersion brut vs corrigé (Tab. 3-1)")
        tabs.addTab(w3, "Bassins corrigés (Fig. 3-1/3-2)")
        return tabs

    def _actualiser_filtres(self):
        self.combo_participant.setItems(self._participants, check_all=True)
        peupler_combo(self.combo_niveau, self.df_chaussee, 'niveau_effort')

    def _calculer(self):
        if self.df_pesage is None or self.df_pesage.empty:
            QMessageBox.warning(self, "Données manquantes",
                                "Les données de pesage sont nécessaires pour calculer les coefficients.")
            return

        try:
            self._coefficients = calculer_coefficients_correction(self.df_pesage)
            remplir_tableau(self.table_coeff, self._coefficients, fmt_float="{:.4f}")

            ax = self.canvas_coeff.ax()
            if not self._coefficients.empty:
                participants = self._coefficients['participant'].astype(str).values
                alphas = self._coefficients['alpha'].values
                colors = ['#27ae60' if abs(a - 1.0) < 0.05 else '#e67e22' if abs(a - 1.0) < 0.15 else '#e74c3c'
                          for a in alphas]
                ax.bar(participants, alphas, color=colors, edgecolor='black', alpha=0.8)
                ax.axhline(1.0, color='black', linewidth=1, linestyle='--')
                ax.set_xlabel('Participant')
                ax.set_ylabel('Coefficient α')
                ax.set_title('Coefficients de correction F_balance = α × F_HWD')
                ax.grid(axis='y', alpha=0.4)
                ax.set_ylim(0.9, max(alphas) * 1.1)
            self.canvas_coeff.tracer()

            QMessageBox.information(self, "Coefficients calculés",
                f"{len(self._coefficients)} coefficients de correction déterminés.\n"
                "Utilisez 'Comparer' pour voir l'impact sur les dispersions.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def _comparer(self):
        if not self._guard_chaussee():
            return
        if self._coefficients is None or self._coefficients.empty:
            QMessageBox.warning(self, "Coefficients manquants",
                                "Calculez d'abord les coefficients de correction.")
            return
        selected = self.combo_participant.checkedItems()
        if not selected:
            QMessageBox.information(self, "Sélection vide",
                                    "Sélectionnez au moins un participant.")
            return

        niv_val = self.combo_niveau.currentText()
        niveau = None
        if niv_val != "Tous":
            try:
                niveau = int(niv_val)
            except ValueError:
                niveau = None

        df_filtered = self.df_chaussee[self.df_chaussee['participant'].isin(selected)]
        col_deflexions = [c for c in DEFLEXION_COLS if c in df_filtered.columns]

        try:
            # Appliquer la correction
            df_corr = appliquer_correction_effort(df_filtered, self._coefficients)
            corr_cols = [c + '_corr' for c in col_deflexions if c + '_corr' in df_corr.columns]

            # Dispersion brute
            df_app_brut = calculer_dispersion_inter_appareils(
                df_filtered, col_deflexions, niveau_effort=niveau)

            # Dispersion corrigée
            df_app_corr = calculer_dispersion_inter_appareils(
                df_corr, corr_cols, niveau_effort=niveau)

            # Tableau comparatif
            if not df_app_brut.empty:
                cv_brut_cols = [c + '_CV_pct' for c in col_deflexions if c + '_CV_pct' in df_app_brut.columns]
                cv_corr_cols = [c + '_corr_CV_pct' for c in col_deflexions if c + '_corr_CV_pct' in df_app_corr.columns]

                import pandas as pd
                comparatif = pd.DataFrame({
                    'Géophone': col_deflexions[:len(cv_brut_cols)],
                    'CV brut (%)': df_app_brut[cv_brut_cols].mean().values if cv_brut_cols else [],
                    'CV corrigé (%)': df_app_corr[cv_corr_cols].mean().values if cv_corr_cols else [],
                })
                if 'CV brut (%)' in comparatif.columns and 'CV corrigé (%)' in comparatif.columns:
                    comparatif['Réduction (%)'] = comparatif['CV brut (%)'] - comparatif['CV corrigé (%)']
                remplir_tableau(self.table_comp, comparatif, fmt_float="{:.2f}")

                ax = self.canvas_comp.ax()
                x = np.arange(len(comparatif))
                width = 0.35
                ax.bar(x - width/2, comparatif['CV brut (%)'].values, width,
                       label='Efforts bruts', color='coral', edgecolor='black', alpha=0.8)
                ax.bar(x + width/2, comparatif['CV corrigé (%)'].values, width,
                       label='Efforts corrigés', color='steelblue', edgecolor='black', alpha=0.8)
                ax.set_xticks(x)
                ax.set_xticklabels(comparatif['Géophone'].values, fontsize=9)
                ax.set_xlabel('Géophone')
                ax.set_ylabel('CV inter-appareils (%)')
                ax.set_title(f'Dispersion inter-appareils — brut vs corrigé (Niveau {niv_val})')
                ax.legend(fontsize=10)
                ax.grid(axis='y', alpha=0.4)
                self.canvas_comp.tracer()

            # Bassins corrigés moyens par participant
            df_work = df_corr.copy()
            if niveau is not None and 'niveau_effort' in df_work.columns:
                df_work = df_work[df_work['niveau_effort'] == niveau]

            ax3 = self.canvas_bassins.ax()
            if 'participant' in df_work.columns and corr_cols:
                participants = sorted(df_work['participant'].dropna().unique())
                cmap = mplcm.get_cmap('tab10', len(participants))
                import pandas as pd
                bassins_data = []
                for i, app in enumerate(participants):
                    sub = df_work[df_work['participant'] == app]
                    if sub.empty:
                        continue
                    vals = []
                    for cc in corr_cols:
                        v = (sub[cc] / sub['Fmax_kN']).mean() if 'Fmax_kN' in sub.columns else sub[cc].mean()
                        vals.append(v)
                    ax3.plot(GEOPHONE_DISTANCES[:len(vals)], vals,
                             marker='o', markersize=5, color=cmap(i), label=str(app))
                    bassins_data.append({'participant': app, **{corr_cols[j]: vals[j] for j in range(len(vals))}})

                if bassins_data:
                    remplir_tableau(self.table_bassins, pd.DataFrame(bassins_data), fmt_float="{:.4f}")

                ax3.set_xlabel('Distance au centre de chargement (cm)')
                ax3.set_ylabel('Déflexion corrigée / F (µm/kN)')
                ax3.set_title(f'Bassins de déflexion corrigés — Niveau {niv_val}')
                ax3.legend(fontsize=9)
                ax3.grid(True, alpha=0.4)
                ax3.invert_yaxis()
            self.canvas_bassins.tracer()

        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
