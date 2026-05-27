import os
import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
    QMessageBox, QLabel, QSizePolicy, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal

from Calcul.Calculs_portance import charger_excel_brut
from Interfaces.widgets_communs import bouton, separateur, description, LABEL_STYLE

XLS_DEFAULT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'Formatage_data_ex_STAC_Dynatest.xls')
)


class AccueilTab(QWidget):
    donnees_chargees = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._fichiers: list[str] = []
        self.donnees = {}
        self._build_ui()
        if os.path.exists(XLS_DEFAULT):
            self._ajouter_fichier(XLS_DEFAULT)
            self._charger()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(60, 50, 60, 50)
        layout.setSpacing(22)

        # En-tête
        titre = QLabel("STAC — Portance des pistes (HWD / FWD)")
        titre.setStyleSheet("font-size: 26px; font-weight: bold; color: #2c3e50; letter-spacing: 1px;")
        layout.addWidget(titre)
        layout.addWidget(description(
            "Interface d'analyse des essais de portance sur chaussée souple — "
            "campagnes interlaboratoires STAC 2022."
        ))
        layout.addWidget(separateur())

        # Liste de fichiers
        layout.addWidget(QLabel("<b>Fichiers de données brutes (.xls / .xlsx)</b>"))

        self.list_fichiers = QListWidget()
        self.list_fichiers.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_fichiers.setMaximumHeight(120)
        self.list_fichiers.setStyleSheet(
            "font-size: 12px; background: #f4f6f7; "
            "border: 1px solid #d5d8dc; border-radius: 4px;"
        )
        layout.addWidget(self.list_fichiers)

        btn_row = QHBoxLayout()
        btn_add = bouton("＋  Ajouter fichier(s)…", primary=False)
        btn_add.clicked.connect(self._parcourir)
        btn_row.addWidget(btn_add)
        btn_del = bouton("－  Retirer sélection", primary=False)
        btn_del.clicked.connect(self._retirer_selectionnes)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Statut
        self.info_label = QLabel("Aucun fichier chargé.")
        self.info_label.setStyleSheet(LABEL_STYLE)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        layout.addStretch()

        btn_charger = bouton("⟳  Charger les données")
        btn_charger.setFixedHeight(44)
        btn_charger.setStyleSheet(btn_charger.styleSheet() + "font-size: 15px;")
        btn_charger.clicked.connect(self._charger)
        layout.addWidget(btn_charger, alignment=Qt.AlignHCenter)

        self.setLayout(layout)

    def _ajouter_fichier(self, path: str):
        if path not in self._fichiers:
            self._fichiers.append(path)
            self.list_fichiers.addItem(QListWidgetItem(path))

    def _parcourir(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Sélectionner les fichiers Excel",
            os.path.dirname(self._fichiers[-1]) if self._fichiers else "",
            "Fichiers Excel (*.xls *.xlsx)"
        )
        for path in paths:
            self._ajouter_fichier(path)

    def _retirer_selectionnes(self):
        for item in self.list_fichiers.selectedItems():
            path = item.text()
            if path in self._fichiers:
                self._fichiers.remove(path)
            self.list_fichiers.takeItem(self.list_fichiers.row(item))

    def _charger(self):
        if not self._fichiers:
            QMessageBox.warning(self, "Aucun fichier", "Ajoutez au moins un fichier avant de charger.")
            return

        resultats_par_fichier = []
        erreurs = []
        for path in self._fichiers:
            try:
                resultats_par_fichier.append((os.path.basename(path), charger_excel_brut(path)))
            except Exception as e:
                erreurs.append(f"{os.path.basename(path)} : {e}")

        if erreurs:
            QMessageBox.critical(self, "Erreur(s) de chargement", "\n".join(erreurs))
            if not resultats_par_fichier:
                return

        # Fusionner les DataFrames de même clé
        cles = set()
        for _, d in resultats_par_fichier:
            cles.update(d.keys())

        self.donnees = {}
        lignes = []
        for cle in sorted(cles):
            frames = [d[cle] for _, d in resultats_par_fichier if cle in d and hasattr(d[cle], 'shape') and not d[cle].empty]
            if frames:
                df_merge = pd.concat(frames, ignore_index=True)
                self.donnees[cle] = df_merge
                lignes.append(f"  ✔  <b>{cle}</b> : {df_merge.shape[0]} lignes × {df_merge.shape[1]} colonnes")
            else:
                lignes.append(f"  ⚠  <b>{cle}</b> : vide ou non parsé")

        nb_fichiers = len(resultats_par_fichier)
        en_tete = f"<b>Données chargées ({nb_fichiers} fichier{'s' if nb_fichiers > 1 else ''}) :</b>"
        self.info_label.setText("<br>".join([en_tete] + lignes))
        self.donnees_chargees.emit(self.donnees)

    def get_donnees(self):
        return self.donnees
