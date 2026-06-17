import matplotlib.cm as mplcm

from PyQt5.QtWidgets import (
    QLabel, QComboBox, QMessageBox,
    QListWidget, QAbstractItemView, QWidget, QHBoxLayout, QVBoxLayout
)

from Calcul.Calculs_portance import DEFLEXION_COLS, GEOPHONE_DISTANCES
from Interfaces.onglet_base import OngletCanvasSeul
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df, CheckableComboBox


class ComparaisonTab(OngletCanvasSeul):
    titre_onglet  = "Comparaison entre participants / points d'essai"
    desc_onglet   = ("Superpose les bassins de déflexion moyens. "
                     "Cochez les participants ou points à comparer.")
    canvas_figsize = (9, 5)

    def _build_controls(self):
        # Ligne 1 : mode, niveau, déflexion, bouton
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Participant", "Point d'essai"])
        self.combo_mode.currentIndexChanged.connect(self._on_mode_change)
        self.combo_niveau = QComboBox(); self.combo_niveau.addItem("Tous")
        self.combo_col = QComboBox()
        for c in DEFLEXION_COLS:
            self.combo_col.addItem(c)
        btn = bouton("Comparer")
        btn.clicked.connect(self._comparer)

        ligne1 = self._ctrl_row(
            QLabel("Comparer par :"), self.combo_mode,
            QLabel("Niveau :"), self.combo_niveau,
            QLabel("Déflexion :"), self.combo_col,
            None, btn
        )

        # Ligne 2 : liste de sélection avec cases à cocher
        self.label_liste = QLabel("Participants disponibles :")
        self.check_combo_list = CheckableComboBox()
        self.check_combo_list.setMinimumWidth(250)

        ligne2 = QWidget()
        h = QHBoxLayout(ligne2)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(self.label_liste)
        h.addWidget(self.check_combo_list)
        h.addStretch()

        # Conteneur vertical des deux lignes
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(ligne1)
        v.addWidget(ligne2)
        return container

    def _actualiser_filtres(self):
        peupler_combo(self.combo_niveau, self.df_chaussee, 'niveau_effort')
        self._on_mode_change()

    def _on_mode_change(self):
        mode = self.combo_mode.currentText()
        if mode == "Participant":
            self.label_liste.setText("Participants disponibles :")
            self.check_combo_list.setItems(self._participants, check_all=True)
        else:
            self.label_liste.setText("Points disponibles :")
            if self.df_chaussee is not None and 'point' in self.df_chaussee.columns:
                points = sorted(str(v) for v in self.df_chaussee['point'].dropna().unique())
                self.check_combo_list.setItems(points, check_all=True)

    def _comparer(self):
        if not self._guard_chaussee():
            return
        selected = self.check_combo_list.checkedItems()
        if not selected:
            QMessageBox.information(self, "Sélection vide",
                                    "Cochez au moins un élément.")
            return

        df        = appliquer_filtre_df(self.df_chaussee, 'niveau_effort',
                                        self.combo_niveau.currentText())
        mode      = self.combo_mode.currentText()
        col_group = 'participant' if mode == "Participant" else 'point'
        niveau    = self.combo_niveau.currentText()

        ax   = self.canvas.ax()
        cmap = mplcm.get_cmap('tab10', len(selected))
        for i, val in enumerate(selected):
            sub    = df[df[col_group] == val] if col_group in df.columns else df
            d_cols = [c for c in DEFLEXION_COLS if c in sub.columns]
            if not d_cols:
                continue
            ax.plot(GEOPHONE_DISTANCES[:len(d_cols)], sub[d_cols].mean().values,
                    marker='o', markersize=5, color=cmap(i), label=str(val))

        ax.set_xlabel('Distance au centre de charge (cm)')
        ax.set_ylabel('Déflexion moyenne (µm)')
        ax.set_title(f"Comparaison — {mode} | Niveau {niveau}")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.4)
        ax.invert_yaxis()
        self.canvas.tracer()
