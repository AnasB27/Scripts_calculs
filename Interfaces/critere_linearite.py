"""Onglet dédié au critère de linéarité R² (Figures 2-10, 2-11, Annexe C du rapport)."""
from PyQt5.QtWidgets import QLabel, QComboBox, QMessageBox

from Calcul.Calculs_portance import (
    calculer_critere_linearite, tracer_r2_linearite, DEFLEXION_COLS
)
from Interfaces.onglet_base import OngletTableauCanvas
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df, CheckableComboBox


class CritereLineariteTab(OngletTableauCanvas):
    titre_onglet = "Critère de linéarité (R²)"
    desc_onglet = ("Coefficient de détermination R² de la régression déflexion vs force "
                   "par participant, point et passage. "
                   "Seuils : R² ≥ 0.987 (HWD) / R² ≥ 0.973 (FWD). "
                   "(Figures 2-10, 2-11 et Annexe C du rapport EC 2022)")
    splitter_sizes = [420, 480]

    def _build_controls(self):
        self.combo_participant = CheckableComboBox()
        self.combo_participant.setMinimumWidth(160)
        btn = bouton("Calculer R²")
        btn.clicked.connect(self._calculer)
        return self._ctrl_row(
            QLabel("Participant :"), self.combo_participant,
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
        df = self.df_chaussee[self.df_chaussee['participant'].isin(selected)]
        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]

        try:
            df_r2 = calculer_critere_linearite(df, col_deflexions)
            if df_r2.empty:
                QMessageBox.information(self, "Résultat",
                    "Impossible de calculer R² (minimum 3 niveaux d'effort requis).")
                return

            self._afficher_tableau_canvas(
                df_r2,
                lambda ax: tracer_r2_linearite(df_r2, col_deflexions, ax=ax,
                    titre=f"Critère de linéarité — {', '.join(selected)}"),
                fmt_float="{:.6f}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
