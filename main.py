import sys
import os

# Doit être configuré avant tout import matplotlib
import matplotlib
matplotlib.use('Qt5Agg')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QStatusBar, QLabel
from PyQt5.QtGui import QFont

from Interfaces.accueil import AccueilTab
from Interfaces.pesage import PesageTab
from Interfaces.bassins import BassinsTab
from Interfaces.repetabilite import RepetabiliteTab
from Interfaces.linearite import LineariteTab
from Interfaces.bouclage import BouclageTab
from Interfaces.chute_rep import ChuteRepresentativeTab
from Interfaces.comparaison import ComparaisonTab
from Interfaces.edition import EditionTab


APP_STYLE = """
QMainWindow, QWidget {
    background-color: #f5f6fa;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: #2c3e50;
}
QTabWidget::pane {
    border: 1px solid #d5d8dc;
    border-radius: 4px;
    background: #ffffff;
}
QTabBar::tab {
    background: #dfe4ea;
    color: #2c3e50;
    padding: 8px 18px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: #2980b9;
    color: white;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background: #c8d6e5;
}
QComboBox {
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    padding: 3px 8px;
    background: white;
    min-width: 80px;
}
QComboBox:focus { border-color: #2980b9; }
QTableWidget {
    border: 1px solid #d5d8dc;
    gridline-color: #ecf0f1;
    background: white;
    alternate-background-color: #f4f6f7;
}
QTableWidget::item:selected {
    background-color: #2980b9;
    color: white;
}
QHeaderView::section {
    background-color: #2c3e50;
    color: white;
    padding: 5px 8px;
    border: none;
    font-weight: bold;
    font-size: 12px;
}
QSplitter::handle { background: #d5d8dc; width: 3px; height: 3px; }
QCheckBox::indicator { width: 14px; height: 14px; }
QScrollBar:vertical {
    width: 10px; background: #f4f6f7;
    border: none; border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #bdc3c7; border-radius: 5px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STAC — Portance des pistes (HWD / FWD)")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self.accueil_tab     = AccueilTab()
        self.edition_tab     = EditionTab()
        self.pesage_tab      = PesageTab()
        self.bassins_tab     = BassinsTab()
        self.repet_tab       = RepetabiliteTab()
        self.lin_tab         = LineariteTab()
        self.bouclage_tab    = BouclageTab()
        self.chute_rep_tab   = ChuteRepresentativeTab()
        self.comparaison_tab = ComparaisonTab()

        self._tabs.addTab(self.accueil_tab,     "  Accueil  ")
        self._tabs.addTab(self.edition_tab,     "  ✏  Données  ")
        self._tabs.addTab(self.pesage_tab,      "  Pesage dynamique  ")
        self._tabs.addTab(self.bassins_tab,     "  Bassins  ")
        self._tabs.addTab(self.repet_tab,       "  Répétabilité  ")
        self._tabs.addTab(self.lin_tab,         "  Linéarité  ")
        self._tabs.addTab(self.bouclage_tab,    "  Bouclage  ")
        self._tabs.addTab(self.chute_rep_tab,   "  Chute représentative  ")
        self._tabs.addTab(self.comparaison_tab, "  Comparaison  ")

        # Chargement initial → onglet édition + onglets d'analyse
        self.accueil_tab.donnees_chargees.connect(self.edition_tab.set_donnees)
        self.accueil_tab.donnees_chargees.connect(self._propager_donnees)
        self.accueil_tab.donnees_chargees.connect(self._maj_statut)
        # Modifications validées → onglets d'analyse
        self.edition_tab.donnees_modifiees.connect(self._propager_donnees)
        self.edition_tab.donnees_modifiees.connect(self._maj_statut)

        self.setCentralWidget(self._tabs)

        # Barre de statut
        self._status = QStatusBar()
        self._status.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        self.setStatusBar(self._status)
        self._status.showMessage("Prêt — chargez un fichier depuis l'onglet Accueil.")

    def _propager_donnees(self, donnees: dict):
        for tab in [self.pesage_tab, self.bassins_tab, self.repet_tab,
                    self.lin_tab, self.bouclage_tab, self.chute_rep_tab,
                    self.comparaison_tab]:
            try:
                tab.set_donnees(donnees)
            except Exception:
                pass

    def _maj_statut(self, donnees: dict):
        df_c = donnees.get('chaussee')
        df_p = donnees.get('pesage')
        msg_parts = []
        if df_c is not None and not df_c.empty:
            nb_pts = df_c['point'].nunique() if 'point' in df_c.columns else '?'
            msg_parts.append(f"Chaussée : {len(df_c)} mesures, {nb_pts} points")
        if df_p is not None and not df_p.empty:
            msg_parts.append(f"Pesage : {len(df_p)} mesures")
        self._status.showMessage("  |  ".join(msg_parts) if msg_parts else "Données chargées.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
