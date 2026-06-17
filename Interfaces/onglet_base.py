"""
Hiérarchie de classes de base pour les onglets d'analyse.

OngletBase (QWidget, ABC)
├── OngletTableauCanvas      — splitter QTableWidget | NavigationCanvas
│   ├── PesageTab
│   ├── BouclageTab
│   ├── ChuteRepresentativeTab
│   └── RepetabiliteTab      (override _build_content : 2 sous-onglets)
├── OngletDoubleCanvas       — 2 NavigationCanvas côte à côte
│   └── LineariteTab
└── OngletCanvasSeul         — 1 NavigationCanvas plein cadre
    ├── BassinsTab
    └── ComparaisonTab
"""

from abc import ABCMeta, abstractmethod

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTableWidget, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt

from Interfaces.widgets_communs import (
    titre, description, separateur, NavigationCanvas, remplir_tableau
)


# Métaclasse combinée : métaclasse Qt (récupérée depuis QWidget) + ABCMeta
class _MetaOnglet(type(QWidget), ABCMeta):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Classe racine
# ─────────────────────────────────────────────────────────────────────────────

class OngletBase(QWidget, metaclass=_MetaOnglet):
    """
    Classe mère de tous les onglets d'analyse.

    Sous-classes responsables de :
      - définir `titre_onglet` et `desc_onglet` (attributs de classe)
      - implémenter `_build_controls()` — barre filtres/boutons
      - implémenter `_run()` — logique déclenchée par le bouton principal
      - appeler `_actualiser_filtres()` si elles ont des combos
    """

    titre_onglet: str = ""
    desc_onglet:  str = ""

    def __init__(self):
        super().__init__()
        self.df_chaussee = None
        self.df_pesage   = None
        self._participants = []

        self._root = QVBoxLayout()
        self._root.setContentsMargins(20, 16, 20, 16)
        self._root.setSpacing(6)          # ← serré : pas d'espace mort

        # En-tête commun
        if self.titre_onglet:
            self._root.addWidget(titre(self.titre_onglet))
        if self.desc_onglet:
            self._root.addWidget(description(self.desc_onglet))
        self._root.addWidget(separateur())

        # Zone de filtres (implémentée par la sous-classe)
        ctrl_widget = self._build_controls()
        if ctrl_widget is not None:
            self._root.addWidget(ctrl_widget)

        # Zone de contenu principale (tableau, canvas, etc.)
        content = self._build_content()
        self._root.addWidget(content, stretch=1)   # ← stretch=1 : occupe tout l'espace restant

        self.setLayout(self._root)

    # ── Interface à implémenter ───────────────────────────────────────────────

    @abstractmethod
    def _build_controls(self) -> QWidget:
        """Retourne un QWidget contenant les filtres et le bouton d'action."""

    @abstractmethod
    def _build_content(self) -> QWidget:
        """Retourne le widget de contenu principal (splitter, canvas…)."""

    # ── Données ───────────────────────────────────────────────────────────────

    def set_donnees(self, donnees: dict):
        self.df_chaussee = donnees.get('chaussee')
        self.df_pesage   = donnees.get('pesage')
        self._participants = []
        if self.df_chaussee is not None and 'participant' in self.df_chaussee.columns:
            self._participants = sorted(self.df_chaussee['participant'].dropna().unique().tolist())
        self._actualiser_filtres()

    def _actualiser_filtres(self):
        """Surcharger pour peupler les combos à la réception des données."""

    # ── Garde-fous réutilisables ──────────────────────────────────────────────

    def _guard_chaussee(self) -> bool:
        if self.df_chaussee is None or self.df_chaussee.empty:
            QMessageBox.warning(self, "Données manquantes",
                                "Chargez un fichier depuis l'onglet Accueil.")
            return False
        return True

    def _guard_pesage(self) -> bool:
        if self.df_pesage is None or self.df_pesage.empty:
            QMessageBox.warning(self, "Données manquantes",
                                "Aucune donnée de pesage disponible.")
            return False
        return True

    # ── Utilitaire barre de contrôles ─────────────────────────────────────────

    @staticmethod
    def _ctrl_row(*widgets) -> QWidget:
        """Emballe des widgets dans une QHBoxLayout et retourne le QWidget."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(8)
        for item in widgets:
            if item is None:
                h.addStretch()
            elif isinstance(item, QHBoxLayout):
                h.addLayout(item)
            else:
                h.addWidget(item)
        return w


# ─────────────────────────────────────────────────────────────────────────────
# Intermédiaires
# ─────────────────────────────────────────────────────────────────────────────

class OngletTableauCanvas(OngletBase):
    """
    Onglet avec un QTableWidget à gauche et un NavigationCanvas à droite.
    Sous-classe peut surcharger `splitter_sizes` pour ajuster les proportions.
    """

    splitter_sizes: list = [400, 500]
    canvas_figsize: tuple = (6, 4)

    def _build_content(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.table = QTableWidget()
        self.table.setMinimumWidth(280)
        splitter.addWidget(self.table)

        self.canvas = NavigationCanvas(figsize=self.canvas_figsize)
        wc = QWidget()
        vb = QVBoxLayout(wc)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(0)
        vb.addWidget(self.canvas.get_toolbar())
        vb.addWidget(self.canvas, stretch=1)
        splitter.addWidget(wc)

        splitter.setSizes(self.splitter_sizes)
        splitter.setStretchFactor(0, 0)   # tableau : taille fixe
        splitter.setStretchFactor(1, 1)   # canvas  : s'étend

        return splitter

    def _afficher_tableau_canvas(self, df, tracer_fn, fmt_float="{:.4f}"):
        """Remplit le tableau et trace le graphique en une seule ligne."""
        remplir_tableau(self.table, df, fmt_float=fmt_float)
        ax = self.canvas.ax()
        tracer_fn(ax)
        self.canvas.tracer()


class OngletDoubleCanvas(OngletBase):
    """Onglet avec deux NavigationCanvas côte à côte."""

    canvas_figsize: tuple = (5, 4)

    def _build_content(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        for attr in ('canvas1', 'canvas2'):
            cv = NavigationCanvas(figsize=self.canvas_figsize)
            wc = QWidget()
            vb = QVBoxLayout(wc)
            vb.setContentsMargins(0, 0, 0, 0)
            vb.setSpacing(0)
            vb.addWidget(cv.get_toolbar())
            vb.addWidget(cv, stretch=1)
            splitter.addWidget(wc)
            setattr(self, attr, cv)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        return splitter


class OngletCanvasSeul(OngletBase):
    """Onglet avec un seul NavigationCanvas plein cadre."""

    canvas_figsize: tuple = (9, 5)

    def _build_content(self) -> QWidget:
        self.canvas = NavigationCanvas(figsize=self.canvas_figsize)
        wc = QWidget()
        vb = QVBoxLayout(wc)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(0)
        vb.addWidget(self.canvas.get_toolbar())
        vb.addWidget(self.canvas, stretch=1)
        wc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return wc
