from PyQt5.QtWidgets import (
    QLabel, QComboBox, QMessageBox,
    QWidget, QVBoxLayout, QSplitter, QTableWidget, QTabWidget, QSizePolicy
)
from PyQt5.QtCore import Qt

from Calcul.Calculs_portance import (
    calculer_bouclage, tracer_bouclage,
    calculer_bouclage_detaille, tracer_bouclage_detaille, DEFLEXION_COLS
)
from Interfaces.onglet_base import OngletBase
from Interfaces.widgets_communs import (
    bouton, NavigationCanvas, remplir_tableau, peupler_combo, appliquer_filtre_df,
    CheckableComboBox
)


class BouclageTab(OngletBase):
    titre_onglet = "Étude de bouclage"
    desc_onglet = ("Compare les déflexions à 250 kN en début (N1) et fin de cycle (N7). "
                   "Onglet 1 : delta bouclage par point. "
                   "Onglet 2 : écarts moyens par géophone (Fig. 2-12 à 2-15).")

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
            QLabel("Déflexion :"), self.combo_col,
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
            tbl.setMinimumWidth(280)
            sp.addWidget(tbl)
            cv = NavigationCanvas(figsize=(6, 4))
            wc = QWidget()
            vb = QVBoxLayout(wc)
            vb.setContentsMargins(0, 0, 0, 0)
            vb.setSpacing(0)
            vb.addWidget(cv.get_toolbar())
            vb.addWidget(cv, stretch=1)
            sp.addWidget(wc)
            sp.setSizes([380, 500])
            sp.setStretchFactor(0, 0)
            sp.setStretchFactor(1, 1)
            lv.addWidget(sp, stretch=1)
            return w, tbl, cv

        w1, self.table_simple, self.canvas_simple = _make_sub()
        w2, self.table_detail, self.canvas_detail = _make_sub()
        tabs.addTab(w1, "Bouclage par point (Fig. 2-12)")
        tabs.addTab(w2, "Écarts par géophone (Fig. 2-13 à 2-15)")
        return tabs

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
        col = self.combo_col.currentText()

        # Bouclage simple
        try:
            df_b = calculer_bouclage(df, col_deflexion=col)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
            return
        if df_b.empty:
            QMessageBox.information(self, "Bouclage",
                                    "Impossible de calculer : niveaux 1 et 7 requis.")
            return
        remplir_tableau(self.table_simple, df_b)
        ax1 = self.canvas_simple.ax()
        tracer_bouclage(df_b, ax=ax1)
        self.canvas_simple.tracer()

        # Bouclage détaillé (écarts par géophone, Figure 2-13)
        try:
            col_deflexions = [c for c in DEFLEXION_COLS if c in df.columns]
            df_detail = calculer_bouclage_detaille(df, col_deflexions)
            if not df_detail.empty:
                ecart_cols = [c + '_ecart_pct' for c in col_deflexions if c + '_ecart_pct' in df_detail.columns]
                display_cols = [c for c in ['participant', 'point', 'passage'] + ecart_cols if c in df_detail.columns]
                remplir_tableau(self.table_detail, df_detail[display_cols], fmt_float="{:.3f}")
                ax2 = self.canvas_detail.ax()
                tracer_bouclage_detaille(df_detail, col_deflexions, ax=ax2,
                    titre=f"Bouclage détaillé — {', '.join(selected)}")
                self.canvas_detail.tracer()
        except Exception as e:
            QMessageBox.warning(self, "Bouclage détaillé", str(e))
