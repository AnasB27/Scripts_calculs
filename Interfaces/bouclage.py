from PyQt5.QtWidgets import QLabel, QComboBox, QMessageBox

from Calcul.Calculs_portance import calculer_bouclage, tracer_bouclage, DEFLEXION_COLS
from Interfaces.onglet_base import OngletTableauCanvas
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df


class BouclageTab(OngletTableauCanvas):
    titre_onglet   = "Étude de bouclage"
    desc_onglet    = ("Compare les déflexions à 250 kN en début (N1) et fin de cycle (N7). "
                      "Un bouclage proche de 0 % indique une chaussée stable.")
    splitter_sizes = [400, 460]

    def _build_controls(self):
        self.combo_app = QComboBox(); self.combo_app.addItem("Tous")
        self.combo_col = QComboBox()
        for c in DEFLEXION_COLS:
            self.combo_col.addItem(c)
        btn = bouton("Calculer")
        btn.clicked.connect(self._calculer)
        return self._ctrl_row(
            QLabel("Appareil :"), self.combo_app,
            QLabel("Déflexion :"), self.combo_col,
            None, btn
        )

    def _actualiser_filtres(self):
        peupler_combo(self.combo_app, self.df_chaussee, 'appareil')

    def _calculer(self):
        if not self._guard_chaussee():
            return
        df  = appliquer_filtre_df(self.df_chaussee, 'appareil', self.combo_app.currentText())
        col = self.combo_col.currentText()
        try:
            df_b = calculer_bouclage(df, col_deflexion=col)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
            return
        if df_b.empty:
            QMessageBox.information(self, "Bouclage",
                                    "Impossible de calculer : niveaux 1 et 7 requis.")
            return
        self._afficher_tableau_canvas(df_b, lambda ax: tracer_bouclage(df_b, ax=ax))
