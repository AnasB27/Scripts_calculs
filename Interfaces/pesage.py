from PyQt5.QtWidgets import QLabel, QComboBox

from Calcul.Calculs_portance import analyser_pesage, tracer_pesage
from Interfaces.onglet_base import OngletTableauCanvas
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df


class PesageTab(OngletTableauCanvas):
    titre_onglet   = "Vérification du système de pesage dynamique"
    desc_onglet    = ("Contrôle la précision et la répétabilité de la force appliquée "
                      "pour chaque niveau cible (75–250 kN).")
    splitter_sizes = [360, 500]

    def _build_controls(self):
        self.combo_passage = QComboBox()
        self.combo_passage.addItem("Tous")
        btn = bouton("Afficher")
        btn.clicked.connect(self._afficher)
        return self._ctrl_row(QLabel("Passage :"), self.combo_passage, None, btn)

    def _actualiser_filtres(self):
        peupler_combo(self.combo_passage, self.df_pesage, 'passage')

    def _afficher(self):
        if not self._guard_pesage():
            return
        df = appliquer_filtre_df(self.df_pesage, 'passage', self.combo_passage.currentText())
        resume = analyser_pesage(df)
        self._afficher_tableau_canvas(
            resume,
            lambda ax: tracer_pesage(resume, ax=ax),
            fmt_float="{:.3f}"
        )
