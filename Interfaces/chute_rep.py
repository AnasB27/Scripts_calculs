import matplotlib.cm as mplcm

from PyQt5.QtWidgets import QLabel, QComboBox, QMessageBox

from Calcul.Calculs_portance import calculer_chute_representative, DEFLEXION_COLS, GEOPHONE_DISTANCES
from Interfaces.onglet_base import OngletTableauCanvas
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df, CheckableComboBox


class ChuteRepresentativeTab(OngletTableauCanvas):
    titre_onglet   = "Choix de la chute représentative"
    desc_onglet    = ("Identifie la chute la plus proche de la moyenne "
                      "pour chaque groupe (point × niveau × passage).")
    splitter_sizes = [440, 420]

    def _build_controls(self):
        self.combo_participant = CheckableComboBox()
        self.combo_participant.setMinimumWidth(160)
        self.combo_col = QComboBox()
        for c in DEFLEXION_COLS:
            self.combo_col.addItem(c)
        btn = bouton("Calculer")
        btn.clicked.connect(self._calculer)
        return self._ctrl_row(
            QLabel("Participant :"), self.combo_participant,
            QLabel("Déflexion ref. :"), self.combo_col,
            None, btn
        )

    def _actualiser_filtres(self):
        self.combo_participant.setItems(self._participants, check_all=True)

    def _calculer(self):
        if not self._guard_chaussee():
            return
        selected = self.combo_participant.checkedItems()
        if not selected:
            QMessageBox.information(self, "Sélection vide",
                                    "Sélectionnez au moins un participant.")
            return
        df     = self.df_chaussee[self.df_chaussee['participant'].isin(selected)]
        col    = self.combo_col.currentText()
        df_rep = calculer_chute_representative(df, col_deflexion=col)
        if df_rep.empty:
            QMessageBox.information(self, "Résultat", "Aucune chute représentative identifiée.")
            return

        def _tracer(ax):
            d_cols    = [c for c in DEFLEXION_COLS if c in df_rep.columns]
            distances = GEOPHONE_DISTANCES[:len(d_cols)]
            if 'point' in df_rep.columns:
                points = df_rep['point'].dropna().unique()
                cmap   = mplcm.get_cmap('tab10', len(points))
                for i, pt in enumerate(points):
                    sub = df_rep[df_rep['point'] == pt]
                    if not sub.empty:
                        ax.plot(distances, sub[d_cols].mean().values,
                                marker='o', markersize=5, color=cmap(i), label=str(pt))
            else:
                ax.plot(distances, df_rep[d_cols].mean().values, marker='o', color='steelblue')
            ax.set_xlabel('Distance (cm)')
            ax.set_ylabel('Déflexion (µm)')
            ax.set_title("Bassins — chutes représentatives")
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.4)
            ax.invert_yaxis()

        self._afficher_tableau_canvas(df_rep, _tracer, fmt_float="{:.3f}")
