"""Composants réutilisables partagés par tous les onglets."""
import pandas as pd
from PyQt5.QtWidgets import (
    QFrame, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QLabel, QComboBox, QWidget,
    QHBoxLayout, QToolButton, QMenu, QAction, QWidgetAction
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
from matplotlib.figure import Figure


# ── Styles ────────────────────────────────────────────────────────────────────

BTN_PRIMARY = """
    QPushButton {
        background-color: #2980b9; color: white;
        font-weight: bold; font-size: 13px;
        border-radius: 6px; padding: 6px 18px;
        min-width: 80px;
    }
    QPushButton:hover   { background-color: #1f6fa0; }
    QPushButton:pressed { background-color: #1a5c87; }
    QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
"""

BTN_SECONDARY = """
    QPushButton {
        background-color: #ecf0f1; color: #2c3e50;
        font-weight: bold; font-size: 13px;
        border: 1px solid #bdc3c7;
        border-radius: 6px; padding: 6px 18px;
        min-width: 80px;
    }
    QPushButton:hover   { background-color: #d5dbdb; }
    QPushButton:pressed { background-color: #c0c7c7; }
"""

TITRE_STYLE   = "font-size: 18px; font-weight: bold; color: #2c3e50;"
DESC_STYLE    = "color: #7f8c8d; font-size: 12px;"
LABEL_STYLE   = "font-size: 13px; color: #34495e;"


# ── Factories ─────────────────────────────────────────────────────────────────

def bouton(texte: str, primary: bool = True) -> QPushButton:
    btn = QPushButton(texte)
    btn.setStyleSheet(BTN_PRIMARY if primary else BTN_SECONDARY)
    return btn


def separateur() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    return sep


def titre(texte: str) -> QLabel:
    lbl = QLabel(texte)
    lbl.setStyleSheet(TITRE_STYLE)
    return lbl


def description(texte: str) -> QLabel:
    lbl = QLabel(texte)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(DESC_STYLE)
    return lbl


# ── CheckableComboBox ─────────────────────────────────────────────────────────

class CheckableComboBox(QPushButton):
    """Bouton déroulant avec QMenu à cases à cocher pour sélection multiple."""

    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actions = []
        self._menu = QMenu(self)
        self._menu.setStyleSheet(
            "QMenu { font-size: 13px; padding: 4px 0; }"
            "QMenu::item { padding: 6px 16px 6px 8px; }"
            "QMenu::item:selected { background: #eaf2f8; }"
            "QMenu::indicator { width: 16px; height: 16px; margin-left: 6px; }"
        )
        self.setMenu(self._menu)
        self.setStyleSheet(
            "QPushButton { text-align: left; padding: 4px 10px; "
            "border: 1px solid #bdc3c7; border-radius: 4px; "
            "background: white; color: #2c3e50; font-size: 13px; }"
            "QPushButton:hover { border-color: #2980b9; }"
            "QPushButton::menu-indicator { subcontrol-position: right center; "
            "image: none; width: 0; }"
        )
        self.setFixedHeight(28)
        self._update_display()

    def setMinimumWidth(self, w):
        super().setMinimumWidth(w)

    def setItems(self, items: list, check_all: bool = False):
        self._menu.clear()
        self._actions = []
        for text in items:
            action = self._menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(check_all)
            action.triggered.connect(self._on_action_triggered)
            self._actions.append(action)
        self._update_display()

    def checkedItems(self) -> list:
        return [a.text() for a in self._actions if a.isChecked()]

    def selectAll(self):
        for a in self._actions:
            a.setChecked(True)
        self._update_display()
        self.selection_changed.emit()

    def selectNone(self):
        for a in self._actions:
            a.setChecked(False)
        self._update_display()
        self.selection_changed.emit()

    def _on_action_triggered(self):
        self._update_display()
        self.selection_changed.emit()

    def _update_display(self):
        checked = self.checkedItems()
        total = len(self._actions)
        if not checked:
            self.setText("  Sélectionner…  ▾")
        elif len(checked) == total and total > 0:
            self.setText("  Tous  ▾")
        elif len(checked) <= 2:
            self.setText("  " + ", ".join(checked) + "  ▾")
        else:
            self.setText(f"  {len(checked)}/{total} sélectionnés  ▾")


# ── NavigationCanvas ──────────────────────────────────────────────────────────

class NavigationCanvas(FigureCanvas):
    """FigureCanvas + barre d'outils matplotlib intégrée dans un conteneur vertical."""

    graphique_trace = pyqtSignal(object, str)

    def __init__(self, figsize=(8, 4), parent=None):
        self.figure = Figure(figsize=figsize, tight_layout=True)
        super().__init__(self.figure)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

    def get_toolbar(self, parent=None):
        """Retourne la NavigationToolbar à placer au-dessus ou en-dessous du canvas."""
        return NavigationToolbar(self, parent)

    def reset(self):
        self.figure.clear()

    def ax(self, rows=1, cols=1):
        """Retourne les axes (crée des subplots si nécessaire)."""
        self.figure.clear()
        if rows == 1 and cols == 1:
            return self.figure.add_subplot(111)
        return self.figure.subplots(rows, cols)

    def tracer(self, label: str = ""):
        """Redessine le canvas ET enregistre dans l'historique. Appeler à la place de draw()."""
        self.draw()
        if not label:
            axes = self.figure.get_axes()
            if axes and axes[0].get_title():
                label = axes[0].get_title()
            else:
                label = "Graphique"
        self.graphique_trace.emit(self.figure, label)


# ── Tableau ───────────────────────────────────────────────────────────────────

_COL_PAIR  = QColor(245, 248, 250)
_COL_IMPAIR = QColor(255, 255, 255)


def remplir_tableau(table: QTableWidget, df: pd.DataFrame, fmt_float: str = "{:.4f}") -> None:
    """Remplit un QTableWidget depuis un DataFrame avec alternance de couleurs et tri activé."""
    if df is None or df.empty:
        table.setRowCount(0)
        table.setColumnCount(0)
        return

    table.setSortingEnabled(False)
    table.setRowCount(len(df))
    table.setColumnCount(len(df.columns))
    table.setHorizontalHeaderLabels([str(c) for c in df.columns])

    for i, (_, row) in enumerate(df.iterrows()):
        bg = _COL_PAIR if i % 2 == 0 else _COL_IMPAIR
        for j, val in enumerate(row):
            if isinstance(val, float) and not pd.isna(val):
                text = fmt_float.format(val)
            elif pd.isna(val):
                text = ""
            else:
                text = str(val)
            item = QTableWidgetItem(text)
            item.setBackground(bg)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(i, j, item)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setStretchLastSection(True)
    table.setSortingEnabled(True)


# ── Filtres ───────────────────────────────────────────────────────────────────

def appliquer_filtre_df(df: pd.DataFrame, col: str, val: str) -> pd.DataFrame:
    """Applique un filtre sur une colonne si val != 'Tous'. Gère int et str."""
    if val == "Tous" or col not in df.columns:
        return df
    # Essai de conversion numérique
    try:
        return df[df[col] == int(val)]
    except (ValueError, TypeError):
        return df[df[col] == val]


def peupler_combo(combo, df: pd.DataFrame, col: str, with_all: bool = True) -> None:
    """Peuple un QComboBox avec les valeurs uniques triées d'une colonne."""
    combo.blockSignals(True)
    combo.clear()
    if with_all:
        combo.addItem("Tous")
    if df is not None and col in df.columns:
        vals = sorted(df[col].dropna().unique(), key=lambda x: (isinstance(x, float), x))
        for v in vals:
            combo.addItem(str(int(v)) if isinstance(v, float) and v == int(v) else str(v))
    combo.blockSignals(False)
