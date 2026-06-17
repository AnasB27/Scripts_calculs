from PyQt5.QtWidgets import (
    QLabel, QComboBox, QMessageBox,
    QWidget, QVBoxLayout, QSplitter, QTableWidget, QTabWidget, QSizePolicy
)
from PyQt5.QtCore import Qt

from Calcul.Calculs_portance import (
    calculer_repetabilite, calculer_reproductibilite,
    tracer_boxplot_repetabilite, DEFLEXION_COLS
)
from Interfaces.onglet_base import OngletBase
from Interfaces.widgets_communs import (
    bouton, NavigationCanvas, remplir_tableau, peupler_combo, appliquer_filtre_df,
    CheckableComboBox
)


class RepetabiliteTab(OngletBase):
    titre_onglet = "Répétabilité et reproductibilité"
    desc_onglet  = ""

    def _build_controls(self):
        self.combo_participant = CheckableComboBox()
        self.combo_participant.setMinimumWidth(160)
        self.combo_col = QComboBox()
        for c in DEFLEXION_COLS:
            self.combo_col.addItem(c)
        self.combo_group = QComboBox()
        for g in ['point', 'niveau_effort', 'passage']:
            self.combo_group.addItem(g)
        btn = bouton("Calculer")
        btn.clicked.connect(self._calculer)
        return self._ctrl_row(
            QLabel("Participant :"), self.combo_participant,
            QLabel("Déflexion :"),  self.combo_col,
            QLabel("Axe boxplot :"), self.combo_group,
            None, btn
        )

    def _build_content(self) -> QWidget:
        tabs = QTabWidget()
        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        def _make_sub():
            w  = QWidget()
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
            sp.setSizes([340, 500])
            sp.setStretchFactor(0, 0)
            sp.setStretchFactor(1, 1)
            lv.addWidget(sp, stretch=1)
            return w, tbl, cv

        w1, self.table_rep,   self.canvas_rep   = _make_sub()
        w2, self.table_repro, self.canvas_repro = _make_sub()
        tabs.addTab(w1, "Répétabilité (chutes)")
        tabs.addTab(w2, "Reproductibilité (passages)")
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
        df    = self.df_chaussee[self.df_chaussee['participant'].isin(selected)]
        col   = self.combo_col.currentText()
        group = self.combo_group.currentText()

        try:
            rep = calculer_repetabilite(df, col_deflexion=col)
            remplir_tableau(self.table_rep, rep)
            ax = self.canvas_rep.ax()
            tracer_boxplot_repetabilite(df, col=col, groupby=group, ax=ax)
            self.canvas_rep.tracer()
        except Exception as e:
            QMessageBox.warning(self, "Répétabilité", str(e))

        try:
            repro = calculer_reproductibilite(df, col_deflexion=col)
            remplir_tableau(self.table_repro, repro)
            ax2 = self.canvas_repro.ax()
            tracer_boxplot_repetabilite(df, col=col, groupby='point', ax=ax2)
            ax2.set_title(f"Reproductibilité — {col} par point")
            self.canvas_repro.tracer()
        except Exception as e:
            QMessageBox.warning(self, "Reproductibilité", str(e))
