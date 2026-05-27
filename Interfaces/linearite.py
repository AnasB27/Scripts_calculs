from PyQt5.QtWidgets import QLabel, QComboBox

from Calcul.Calculs_portance import calculer_linearite, tracer_linearite, DEFLEXION_COLS
from Interfaces.onglet_base import OngletDoubleCanvas
from Interfaces.widgets_communs import bouton, peupler_combo, appliquer_filtre_df


class LineariteTab(OngletDoubleCanvas):
    titre_onglet = "Étude de linéarité"
    desc_onglet  = ("Proportionnalité déflexion–force : "
                    "gauche = nuage d vs F, droite = ratio moyen d/F par niveau.")

    def _build_controls(self):
        self.combo_app   = QComboBox(); self.combo_app.addItem("Tous")
        self.combo_point = QComboBox(); self.combo_point.addItem("Tous")
        self.combo_col   = QComboBox()
        for c in DEFLEXION_COLS:
            self.combo_col.addItem(c)
        btn = bouton("Tracer")
        btn.clicked.connect(self._tracer)
        return self._ctrl_row(
            QLabel("Appareil :"), self.combo_app,
            QLabel("Point :"),    self.combo_point,
            QLabel("Déflexion :"), self.combo_col,
            None, btn
        )

    def _actualiser_filtres(self):
        peupler_combo(self.combo_app,   self.df_chaussee, 'appareil')
        peupler_combo(self.combo_point, self.df_chaussee, 'point')

    def _tracer(self):
        if not self._guard_chaussee():
            return
        col     = self.combo_col.currentText()
        app_val = self.combo_app.currentText()
        pt_val  = self.combo_point.currentText()
        app_f   = None if app_val == "Tous" else app_val
        point_f = None if pt_val  == "Tous" else pt_val

        df = calculer_linearite(self.df_chaussee, col_deflexion=col)

        ax1 = self.canvas1.ax()
        tracer_linearite(df, col=col, ax=ax1, appareil=app_f, point=point_f)
        self.canvas1.draw()

        df_f = appliquer_filtre_df(df, 'appareil', app_val)
        df_f = appliquer_filtre_df(df_f, 'point', pt_val)
        ax2  = self.canvas2.ax()
        if 'ratio_d_F' in df_f.columns and 'niveau_effort' in df_f.columns:
            moy = df_f.groupby('niveau_effort')['ratio_d_F'].mean()
            ax2.bar([str(int(n)) for n in moy.index], moy.values,
                    color='teal', edgecolor='black', alpha=0.8)
            ax2.set_xlabel("Niveau d'effort")
            ax2.set_ylabel(f"{col} / Fmax (µm/kN)")
            ax2.set_title(f"Ratio {col}/Fmax par niveau")
            ax2.grid(axis='y', alpha=0.4)
        self.canvas2.draw()
