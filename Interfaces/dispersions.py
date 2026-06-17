"""Onglet d'analyse comparative des dispersions inter-participants et inter-points."""
import numpy as np

from PyQt5.QtWidgets import (
    QLabel, QComboBox, QMessageBox,
    QWidget, QVBoxLayout, QSplitter, QTableWidget, QTabWidget, QSizePolicy
)
from PyQt5.QtCore import Qt

from Calcul.Calculs_portance import (
    calculer_dispersion_inter_appareils, calculer_dispersion_inter_points,
    tracer_dispersion_comparative, calculer_cv_moyen_par_appareil,
    calculer_cv_moyen_par_geophone, tracer_cv_par_appareil,
    tracer_cv_par_geophone, DEFLEXION_COLS
)
from Interfaces.onglet_base import OngletBase
from Interfaces.widgets_communs import (
    bouton, NavigationCanvas, remplir_tableau, peupler_combo, appliquer_filtre_df,
    CheckableComboBox
)


class DispersionsTab(OngletBase):
    titre_onglet = "Analyse comparative des dispersions"
    desc_onglet = ("Compare la dispersion inter-appareils à la dispersion inter-points "
                   "(Tableaux 2-10 à 2-15, Figures 2-22 et 2-23 du rapport EC 2022).")

    def _build_controls(self):
        self.combo_participant = CheckableComboBox()
        self.combo_participant.setMinimumWidth(160)
        self.combo_niveau = QComboBox()
        self.combo_niveau.addItem("Tous")
        btn = bouton("Analyser")
        btn.clicked.connect(self._analyser)
        return self._ctrl_row(
            QLabel("Participant :"), self.combo_participant,
            QLabel("Niveau d'effort :"), self.combo_niveau,
            None, btn
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
            sp.setSizes([400, 500])
            sp.setStretchFactor(0, 0)
            sp.setStretchFactor(1, 1)
            lv.addWidget(sp, stretch=1)
            return w, tbl, cv

        w1, self.table_comp, self.canvas_comp = _make_sub()
        w2, self.table_cv_app, self.canvas_cv_app = _make_sub()
        w3, self.table_cv_geo, self.canvas_cv_geo = _make_sub()

        tabs.addTab(w1, "Dispersions comparées (Fig. 2-23)")
        tabs.addTab(w2, "CV inter-appareils (Tab. 2-14)")
        tabs.addTab(w3, "CV par géophone (Fig. 2-7)")
        return tabs

    def _actualiser_filtres(self):
        self.combo_participant.setItems(self._participants, check_all=True)
        peupler_combo(self.combo_niveau, self.df_chaussee, 'niveau_effort')

    def _analyser(self):
        if not self._guard_chaussee():
            return
        selected = self.combo_participant.checkedItems()
        if not selected:
            QMessageBox.information(self, "Sélection vide",
                                    "Sélectionnez au moins un participant.")
            return
        df = self.df_chaussee[self.df_chaussee['participant'].isin(selected)]
        niv_val = self.combo_niveau.currentText()
        niveau = None
        if niv_val != "Tous":
            try:
                niveau = int(niv_val)
            except ValueError:
                niveau = None

        col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]

        try:
            # Dispersions comparées
            df_app = calculer_dispersion_inter_appareils(df, col_deflexions, niveau_effort=niveau)
            df_pts = calculer_dispersion_inter_points(df, col_deflexions, niveau_effort=niveau)

            if not df_app.empty:
                remplir_tableau(self.table_comp, df_app, fmt_float="{:.2f}")
            ax1 = self.canvas_comp.ax()
            if not df_app.empty and not df_pts.empty:
                tracer_dispersion_comparative(df_app, df_pts, col_deflexions, ax=ax1,
                    titre=f"Dispersions comparées — Niveau {niv_val}")
            self.canvas_comp.tracer()

            # CV par participant
            df_filtered = df if niveau is None else df[df['niveau_effort'] == niveau]
            df_cv_app = calculer_cv_moyen_par_appareil(df_filtered, col_deflexions)
            remplir_tableau(self.table_cv_app, df_cv_app, fmt_float="{:.3f}")
            ax2 = self.canvas_cv_app.ax()
            tracer_cv_par_appareil(df_cv_app, col_deflexions, ax=ax2,
                titre=f"CV moyen par participant — Niveau {niv_val}")
            self.canvas_cv_app.tracer()

            # CV par géophone
            cv_geo = calculer_cv_moyen_par_geophone(df_filtered, col_deflexions)
            cv_df = cv_geo.to_frame(name='CV_moyen_%').reset_index()
            cv_df.columns = ['Géophone', 'CV_moyen_%']
            remplir_tableau(self.table_cv_geo, cv_df, fmt_float="{:.3f}")
            ax3 = self.canvas_cv_geo.ax()
            tracer_cv_par_geophone(cv_geo, col_deflexions, ax=ax3,
                titre=f"CV moyen par géophone — Niveau {niv_val}")
            self.canvas_cv_geo.tracer()

        except Exception as e:
            QMessageBox.warning(self, "Erreur", str(e))
