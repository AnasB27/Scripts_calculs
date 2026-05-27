"""Onglet de modification des données brutes."""
import pandas as pd
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QMessageBox,
    QFileDialog, QHeaderView, QAbstractItemView,
    QMenu, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QKeySequence

from Interfaces.widgets_communs import bouton, separateur, titre, description, LABEL_STYLE

# Colonnes numériques par feuille (pour validation à la saisie)
_COLS_NUMERIQUES = {
    'chaussee': {
        'passage', 'zone', 'chainage', 'niveau_effort', 'Fmax_kN', 'chute',
        'd1','d2','d3','d4','d5','d6','d7','d8','d9','d10','d11','d12','d13'
    },
    'pesage': {'passage', 'essai', 'chute', 'Fmax_kN', 'effort_cible_kN'},
}

_ROUGE_ERREUR  = QColor(255, 200, 200)
_ROUGE_MODIF   = QColor(255, 243, 205)   # jaune pâle = cellule modifiée non sauvegardée
_VERT_NEW      = QColor(220, 245, 220)   # vert pâle  = nouvelle ligne
_BLANC         = QColor(255, 255, 255)
_GRIS_PAIR     = QColor(245, 248, 250)

_MAX_UNDO = 30


class EditionTab(QWidget):
    """Onglet d'édition des données : modification, ajout, suppression, sauvegarde."""

    donnees_modifiees = pyqtSignal(dict)   # émet le dict complet après modification

    def __init__(self):
        super().__init__()
        self._donnees_orig: dict  = {}   # données brutes (dict feuille→df)
        self._donnees_edit: dict  = {}   # copies modifiables
        self._feuille_active: str = ''
        self._modifie: bool       = False
        self._undo_stack: list    = []   # pile d'annulation (copies de df)
        self._redo_stack: list    = []
        self._nouvelles_lignes: set = set()   # indices de lignes ajoutées

        self._build_ui()
        self.table.installEventFilter(self)

    # ── Données ───────────────────────────────────────────────────────────────

    def set_donnees(self, donnees: dict):
        """Reçoit le dict {feuille: DataFrame} depuis AccueilTab."""
        if self._modifie:
            rep = QMessageBox.question(
                self, "Modifications non sauvegardées",
                "Des modifications non sauvegardées seront perdues. Continuer ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if rep == QMessageBox.No:
                return

        self._donnees_orig = {k: df.copy() for k, df in donnees.items() if hasattr(df, 'copy')}
        self._donnees_edit = {k: df.copy() for k, df in self._donnees_orig.items()}
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._modifie = False
        self._nouvelles_lignes.clear()

        # Peupler le combo de feuilles
        self.combo_feuille.blockSignals(True)
        self.combo_feuille.clear()
        for k, df in self._donnees_edit.items():
            if hasattr(df, 'columns') and not df.empty:
                self.combo_feuille.addItem(k)
        self.combo_feuille.blockSignals(False)

        if self.combo_feuille.count() > 0:
            self.combo_feuille.setCurrentIndex(0)
            self._changer_feuille(self.combo_feuille.currentText())

        self._maj_statut()

    def _df_actif(self) -> pd.DataFrame:
        return self._donnees_edit.get(self._feuille_active, pd.DataFrame())

    def _set_df_actif(self, df: pd.DataFrame):
        self._donnees_edit[self._feuille_active] = df

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(titre("Modification des données"))
        layout.addWidget(description(
            "Double-cliquez sur une cellule pour la modifier. "
            "Ctrl+Z / Ctrl+Y pour annuler / rétablir. "
            "Ctrl+C / Ctrl+V pour copier-coller (compatible Excel). "
            "Les modifications sont surlignées en jaune jusqu'à la sauvegarde."
        ))
        layout.addWidget(separateur())

        # ── Barre d'outils ─────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        toolbar.addWidget(QLabel("Feuille :"))
        self.combo_feuille = QComboBox()
        self.combo_feuille.setMinimumWidth(130)
        self.combo_feuille.currentTextChanged.connect(self._changer_feuille)
        toolbar.addWidget(self.combo_feuille)

        toolbar.addWidget(separateur_vertical())

        self.btn_ajouter = bouton("＋  Ajouter ligne", primary=False)
        self.btn_ajouter.clicked.connect(self._ajouter_ligne)
        toolbar.addWidget(self.btn_ajouter)

        self.btn_suppr = bouton("－  Supprimer", primary=False)
        self.btn_suppr.clicked.connect(self._supprimer_lignes)
        toolbar.addWidget(self.btn_suppr)

        toolbar.addWidget(separateur_vertical())

        self.btn_undo = bouton("↩  Annuler", primary=False)
        self.btn_undo.setShortcut(QKeySequence.Undo)
        self.btn_undo.clicked.connect(self._undo)
        self.btn_undo.setEnabled(False)
        toolbar.addWidget(self.btn_undo)

        self.btn_redo = bouton("↪  Rétablir", primary=False)
        self.btn_redo.setShortcut(QKeySequence.Redo)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_redo.setEnabled(False)
        toolbar.addWidget(self.btn_redo)

        toolbar.addWidget(separateur_vertical())

        self.btn_reset = bouton("⟳  Réinitialiser", primary=False)
        self.btn_reset.setToolTip("Revenir aux données originales (abandonne toutes les modifications)")
        self.btn_reset.clicked.connect(self._reinitialiser)
        toolbar.addWidget(self.btn_reset)

        toolbar.addStretch()

        self.btn_sauver_csv = bouton("💾  Sauvegarder CSV")
        self.btn_sauver_csv.clicked.connect(self._sauvegarder_csv)
        toolbar.addWidget(self.btn_sauver_csv)

        self.btn_sauver_xl = bouton("📊  Exporter Excel")
        self.btn_sauver_xl.clicked.connect(self._exporter_excel)
        toolbar.addWidget(self.btn_sauver_xl)

        self.btn_appliquer = bouton("✔  Appliquer aux analyses")
        self.btn_appliquer.setToolTip("Propager les modifications courantes vers tous les onglets d'analyse")
        self.btn_appliquer.clicked.connect(self._appliquer)
        toolbar.addWidget(self.btn_appliquer)

        layout.addLayout(toolbar)

        # ── Barre de recherche ─────────────────────────────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_row.addWidget(QLabel("🔍  Rechercher :"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrer les lignes (toutes colonnes)…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filtrer)
        search_row.addWidget(self.search_edit)

        self.lbl_nb_lignes = QLabel("")
        self.lbl_nb_lignes.setStyleSheet(LABEL_STYLE)
        search_row.addWidget(self.lbl_nb_lignes)
        layout.addLayout(search_row)

        # ── Tableau ────────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.AnyKeyPressed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu_contextuel)
        self.table.itemChanged.connect(self._on_cellule_changee)
        layout.addWidget(self.table)

        # ── Barre de statut ────────────────────────────────────────────────
        self.lbl_statut = QLabel("")
        self.lbl_statut.setStyleSheet("font-size: 12px; color: #7f8c8d; padding: 2px 0;")
        layout.addWidget(self.lbl_statut)

        self.setLayout(layout)

    # ── Chargement tableau ─────────────────────────────────────────────────────

    def _changer_feuille(self, nom: str):
        if not nom:
            return
        self._feuille_active = nom
        self._nouvelles_lignes.clear()
        self._charger_tableau()

    def _charger_tableau(self, filtre: str = ""):
        df = self._df_actif()
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        # Filtrage
        if filtre:
            masque = df.apply(
                lambda col: col.astype(str).str.contains(filtre, case=False, na=False)
            ).any(axis=1)
            df_affiche = df[masque]
            # Mémoriser la correspondance ligne affichée → index df original
            self._idx_map = list(df[masque].index)
        else:
            df_affiche = df
            self._idx_map = list(df.index)

        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(df_affiche))
        self.table.setColumnCount(len(df_affiche.columns))
        self.table.setHorizontalHeaderLabels(list(df_affiche.columns))

        cols_num = _COLS_NUMERIQUES.get(self._feuille_active, set())

        for row_idx, (orig_idx, row) in enumerate(df_affiche.iterrows()):
            is_new = orig_idx in self._nouvelles_lignes
            bg_base = _VERT_NEW if is_new else (_GRIS_PAIR if row_idx % 2 == 0 else _BLANC)
            for col_idx, (col_name, val) in enumerate(row.items()):
                text = "" if pd.isna(val) else str(val)
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, orig_idx)   # stocker l'index df original
                item.setBackground(bg_base)
                # Alignement numérique à droite
                if col_name in cols_num:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)

        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self.lbl_nb_lignes.setText(
            f"{len(df_affiche)} / {len(df)} lignes" if filtre else f"{len(df)} lignes"
        )

    # ── Modification cellule ───────────────────────────────────────────────────

    def _on_cellule_changee(self, item: QTableWidgetItem):
        if not self._feuille_active or item is None:
            return

        orig_idx = item.data(Qt.UserRole)
        if orig_idx is None:
            return

        df = self._df_actif()
        col_name = df.columns[item.column()]
        new_text = item.text().strip()

        # Valider le type
        cols_num = _COLS_NUMERIQUES.get(self._feuille_active, set())
        if col_name in cols_num and new_text != "":
            try:
                new_val = float(new_text)
            except ValueError:
                item.setBackground(_ROUGE_ERREUR)
                self.lbl_statut.setText(
                    f"⚠  Valeur invalide pour '{col_name}' (attendu : nombre)"
                )
                return
        else:
            new_val = new_text if new_text != "" else np.nan

        # Empiler l'état avant modification
        self._push_undo()

        df.at[orig_idx, col_name] = new_val
        self._set_df_actif(df)
        item.setBackground(_ROUGE_MODIF)
        self._modifie = True
        self._maj_statut()

    # ── Copier / Coller ────────────────────────────────────────────────────────

    def eventFilter(self, source, event):
        if source is self.table and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.Copy):
                self._copier()
                return True
            if event.matches(QKeySequence.Paste):
                self._coller()
                return True
        return super().eventFilter(source, event)

    def _copier(self):
        ranges = self.table.selectedRanges()
        if not ranges:
            return
        texte = ""
        for r in ranges:
            for i in range(r.topRow(), r.bottomRow() + 1):
                cells = []
                for j in range(r.leftColumn(), r.rightColumn() + 1):
                    item = self.table.item(i, j)
                    cells.append(item.text() if item else "")
                texte += "\t".join(cells) + "\n"
        QApplication.clipboard().setText(texte)

    def _coller(self):
        texte = QApplication.clipboard().text()
        if not texte:
            return

        start_row = self.table.currentRow()
        start_col = self.table.currentColumn()
        if start_row < 0:
            start_row = 0
        if start_col < 0:
            start_col = 0

        self._push_undo()
        self.table.blockSignals(True)

        df = self._df_actif()
        cols_num = _COLS_NUMERIQUES.get(self._feuille_active, set())

        for i, line in enumerate(texte.splitlines()):
            if not line:
                continue
            cells = line.split("\t")
            row_tbl = start_row + i

            # Étendre le DataFrame si nécessaire
            if row_tbl >= self.table.rowCount():
                new_idx = df.index.max() + 1 if not df.empty else 0
                df.loc[new_idx] = [np.nan] * len(df.columns)
                self._nouvelles_lignes.add(new_idx)
                self.table.insertRow(row_tbl)
                for c in range(self.table.columnCount()):
                    it = QTableWidgetItem("")
                    it.setData(Qt.UserRole, new_idx)
                    it.setBackground(_VERT_NEW)
                    self.table.setItem(row_tbl, c, it)

            for j, cell_text in enumerate(cells):
                col_tbl = start_col + j
                if col_tbl >= self.table.columnCount():
                    break
                col_name = df.columns[col_tbl]
                text = cell_text.strip()

                if col_name in cols_num and text:
                    try:
                        val = float(text.replace(",", "."))
                    except ValueError:
                        val = np.nan
                else:
                    val = text if text else np.nan

                orig_idx = self.table.item(row_tbl, 0)
                if orig_idx is not None:
                    oi = orig_idx.data(Qt.UserRole)
                    if oi is not None:
                        df.at[oi, col_name] = val

                item = QTableWidgetItem(text)
                item.setBackground(_ROUGE_MODIF)
                if orig_idx is not None:
                    item.setData(Qt.UserRole, orig_idx.data(Qt.UserRole))
                self.table.setItem(row_tbl, col_tbl, item)

        self._set_df_actif(df)
        self.table.blockSignals(False)
        self._modifie = True
        self._maj_statut()

    # ── Ajout / Suppression ────────────────────────────────────────────────────

    def _ajouter_ligne(self):
        df = self._df_actif()
        if df.empty:
            return
        self._push_undo()
        new_idx = int(df.index.max()) + 1 if not df.empty else 0
        df.loc[new_idx] = [np.nan] * len(df.columns)
        self._nouvelles_lignes.add(new_idx)
        self._set_df_actif(df)
        self._modifie = True

        # Ajouter visuellement sans recharger tout le tableau
        self.table.blockSignals(True)
        row_tbl = self.table.rowCount()
        self.table.insertRow(row_tbl)
        for c, col_name in enumerate(df.columns):
            item = QTableWidgetItem("")
            item.setData(Qt.UserRole, new_idx)
            item.setBackground(_VERT_NEW)
            self.table.setItem(row_tbl, c, item)
        self.table.blockSignals(False)
        self.table.scrollToBottom()
        self.table.setCurrentCell(row_tbl, 0)
        self._maj_statut()

    def _supprimer_lignes(self):
        rows_sel = sorted(set(item.row() for item in self.table.selectedItems()), reverse=True)
        if not rows_sel:
            QMessageBox.information(self, "Aucune sélection", "Sélectionnez au moins une ligne.")
            return

        rep = QMessageBox.question(
            self, "Confirmation",
            f"Supprimer {len(rows_sel)} ligne(s) ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if rep == QMessageBox.No:
            return

        self._push_undo()
        df = self._df_actif()

        orig_indices = []
        for r in rows_sel:
            item = self.table.item(r, 0)
            if item is not None:
                oi = item.data(Qt.UserRole)
                if oi is not None:
                    orig_indices.append(oi)

        df = df.drop(index=orig_indices, errors='ignore').reset_index(drop=True)
        self._nouvelles_lignes -= set(orig_indices)
        self._set_df_actif(df)
        self._modifie = True
        self._charger_tableau(self.search_edit.text())
        self._maj_statut()

    # ── Annuler / Rétablir ─────────────────────────────────────────────────────

    def _push_undo(self):
        df = self._df_actif()
        if df is not None:
            self._undo_stack.append(df.copy())
            if len(self._undo_stack) > _MAX_UNDO:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
        self._maj_boutons_undo()

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._df_actif().copy())
        self._set_df_actif(self._undo_stack.pop())
        self._modifie = True
        self._charger_tableau(self.search_edit.text())
        self._maj_statut()
        self._maj_boutons_undo()

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._df_actif().copy())
        self._set_df_actif(self._redo_stack.pop())
        self._modifie = True
        self._charger_tableau(self.search_edit.text())
        self._maj_statut()
        self._maj_boutons_undo()

    def _maj_boutons_undo(self):
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_redo.setEnabled(bool(self._redo_stack))
        self.btn_undo.setToolTip(f"Annuler ({len(self._undo_stack)} étapes disponibles)")
        self.btn_redo.setToolTip(f"Rétablir ({len(self._redo_stack)} étapes disponibles)")

    def _reinitialiser(self):
        rep = QMessageBox.question(
            self, "Réinitialiser",
            "Toutes les modifications seront annulées. Continuer ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if rep == QMessageBox.No:
            return
        self._donnees_edit = {k: df.copy() for k, df in self._donnees_orig.items()}
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._nouvelles_lignes.clear()
        self._modifie = False
        self._charger_tableau()
        self._maj_statut()
        self._maj_boutons_undo()

    # ── Filtrage ───────────────────────────────────────────────────────────────

    def _filtrer(self, texte: str):
        self._charger_tableau(texte)

    # ── Menu contextuel ────────────────────────────────────────────────────────

    def _menu_contextuel(self, pos):
        menu = QMenu(self)
        menu.addAction("Copier  Ctrl+C",        self._copier)
        menu.addAction("Coller  Ctrl+V",         self._coller)
        menu.addSeparator()
        menu.addAction("Ajouter une ligne",      self._ajouter_ligne)
        menu.addAction("Supprimer ligne(s)",     self._supprimer_lignes)
        menu.addSeparator()
        menu.addAction("Effacer la cellule",     self._effacer_cellule)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _effacer_cellule(self):
        self._push_undo()
        df = self._df_actif()
        for item in self.table.selectedItems():
            col_name = df.columns[item.column()]
            orig_idx = item.data(Qt.UserRole)
            if orig_idx is not None:
                df.at[orig_idx, col_name] = np.nan
            self.table.blockSignals(True)
            item.setText("")
            item.setBackground(_ROUGE_MODIF)
            self.table.blockSignals(False)
        self._set_df_actif(df)
        self._modifie = True
        self._maj_statut()

    # ── Sauvegarde / Export ────────────────────────────────────────────────────

    def _sauvegarder_csv(self):
        if not self._feuille_active:
            return
        df = self._df_actif()
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder en CSV",
            f"{self._feuille_active}_modifie.csv",
            "CSV (*.csv)"
        )
        if not path:
            return
        try:
            df.to_csv(path, index=False)
            self._modifie = False
            self._charger_tableau(self.search_edit.text())  # retire les surlignages
            self._maj_statut()
            QMessageBox.information(self, "Sauvegarde", f"Fichier sauvegardé :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def _exporter_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter en Excel",
            "donnees_portance_modifiees.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                for nom, df in self._donnees_edit.items():
                    if hasattr(df, 'to_excel') and not df.empty:
                        df.to_excel(writer, sheet_name=nom[:31], index=False)
            self._modifie = False
            self._maj_statut()
            QMessageBox.information(self, "Export", f"Fichier Excel exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    # ── Propagation ───────────────────────────────────────────────────────────

    def _appliquer(self):
        self.donnees_modifiees.emit(dict(self._donnees_edit))
        QMessageBox.information(
            self, "Analyses mises à jour",
            "Les modifications ont été propagées vers tous les onglets d'analyse."
        )

    # ── Statut ─────────────────────────────────────────────────────────────────

    def _maj_statut(self):
        df = self._df_actif()
        n = len(df) if not df.empty else 0
        etat = "⚠  Modifications non sauvegardées" if self._modifie else "✔  Aucune modification"
        feuille = self._feuille_active or "—"
        self.lbl_statut.setText(
            f"Feuille : <b>{feuille}</b>   |   Lignes : <b>{n}</b>   |   {etat}"
        )
        self.lbl_statut.setStyleSheet(
            "font-size: 12px; color: #e67e22;" if self._modifie
            else "font-size: 12px; color: #27ae60;"
        )


# ── Widget utilitaire ─────────────────────────────────────────────────────────

def separateur_vertical() -> QWidget:
    """Séparateur vertical fin pour barre d'outils."""
    w = QWidget()
    w.setFixedWidth(1)
    w.setStyleSheet("background: #d5d8dc;")
    return w
