import pandas as pd

from PyQt5.QtWidgets import QLabel, QComboBox, QCheckBox, QMessageBox

from Calcul.Calculs_portance import tracer_bassins_deflexion, tracer_histogramme_deflexion, DEFLEXION_COLS
from Interfaces.onglet_base import OngletCanvasSeul
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df, CheckableComboBox


class BassinsTab(OngletCanvasSeul):
    titre_onglet  = "Bassins de déflexion"
    desc_onglet   = ("Tracé de d1–d13 en fonction de la distance au centre de charge "
                     "pour chaque combinaison appareil / point / niveau / passage.")
    canvas_figsize = (9, 5)

    def _build_controls(self):
        self._combos = {}
        widgets = []

        self.combo_participant = CheckableComboBox()
        self.combo_participant.setMinimumWidth(160)
        widgets += [QLabel("Participant :"), self.combo_participant]

        for label, key in [("Point", "point"),
                            ("Passage", "passage"), ("Niveau", "niveau_effort")]:
            cb = QComboBox(); cb.addItem("Tous")
            self._combos[key] = cb
            widgets += [QLabel(f"{label} :"), cb]

        self.chk_moyenne = QCheckBox("Moyenne des chutes")
        widgets.append(self.chk_moyenne)

        btn = bouton("Tracer")
        btn.clicked.connect(self._tracer)
        btn_histo = bouton("Histogramme", primary=False)
        btn_histo.clicked.connect(self._histogramme)
        widgets += [None, btn, btn_histo]
        return self._ctrl_row(*widgets)

    def _actualiser_filtres(self):
        self.combo_participant.setItems(self._participants, check_all=True)
        for col, cb in self._combos.items():
            peupler_combo(cb, self.df_chaussee, col)

    def _tracer(self):
        if not self._guard_chaussee():
            return
        selected_participants = self.combo_participant.checkedItems()
        if not selected_participants:
            QMessageBox.information(self, "Sélection vide",
                                    "Sélectionnez au moins un participant.")
            return
        df = self.df_chaussee[self.df_chaussee['participant'].isin(selected_participants)].copy()
        labels = {'participant': ', '.join(selected_participants)}
        for col, cb in self._combos.items():
            val = cb.currentText()
            df  = appliquer_filtre_df(df, col, val)
            labels[col] = val

        if df.empty:
            QMessageBox.information(self, "Aucune donnée",
                                    "Aucune mesure ne correspond aux filtres.")
            return

        if self.chk_moyenne.isChecked():
            grp    = [c for c in ['participant', 'point', 'niveau_effort', 'passage'] if c in df.columns]
            d_cols = [c for c in DEFLEXION_COLS if c in df.columns]
            df     = df.groupby(grp)[d_cols + ['Fmax_kN']].mean().reset_index()
            df['chute'] = float('nan')

        ax = self.canvas.ax()
        tracer_bassins_deflexion(
            df, ax=ax,
            titre=(f"Bassin — {labels['participant']} | {labels['point']} | "
                   f"Passage {labels['passage']} | N{labels['niveau_effort']}")
        )
        self.canvas.tracer()

    def _histogramme(self):
        if not self._guard_chaussee():
            return
        selected_participants = self.combo_participant.checkedItems()
        if not selected_participants:
            QMessageBox.information(self, "Sélection vide",
                                    "Sélectionnez au moins un participant.")
            return
        df = self.df_chaussee[self.df_chaussee['participant'].isin(selected_participants)].copy()
        for col, cb in self._combos.items():
            val = cb.currentText()
            df = appliquer_filtre_df(df, col, val)
        if df.empty:
            QMessageBox.information(self, "Aucune donnée",
                                    "Aucune mesure ne correspond aux filtres.")
            return
        col = 'd1'
        d_cols = [c for c in DEFLEXION_COLS if c in df.columns]
        if d_cols:
            col = d_cols[0]
        ax = self.canvas.ax()
        tracer_histogramme_deflexion(df, col=col, ax=ax,
            titre=f"Distribution de {col}")
        self.canvas.tracer()
