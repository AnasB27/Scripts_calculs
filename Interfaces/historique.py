"""Onglet Historique : galerie de miniatures de tous les graphiques générés."""
import io
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGridLayout, QDialog, QSizePolicy, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QCursor

from matplotlib.figure import Figure

from Interfaces.widgets_communs import titre, description, separateur, bouton, LABEL_STYLE


class _Miniature(QFrame):
    """Widget miniature cliquable avec titre et horodatage."""
    clicked = pyqtSignal()

    def __init__(self, pixmap: QPixmap, label: str, timestamp: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(1)
        self.setStyleSheet("""
            _Miniature {
                background: white;
                border: 1px solid #d5d8dc;
                border-radius: 6px;
            }
            _Miniature:hover {
                border: 2px solid #2980b9;
                background: #eaf2f8;
            }
        """)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedSize(240, 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Image miniature
        img_label = QLabel()
        scaled = pixmap.scaled(220, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img_label.setPixmap(scaled)
        img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(img_label)

        # Titre
        txt = QLabel(label)
        txt.setStyleSheet("font-size: 10px; font-weight: bold; color: #2c3e50;")
        txt.setAlignment(Qt.AlignCenter)
        txt.setWordWrap(True)
        txt.setMaximumHeight(28)
        layout.addWidget(txt)

        # Horodatage
        ts = QLabel(timestamp)
        ts.setStyleSheet("font-size: 9px; color: #95a5a6;")
        ts.setAlignment(Qt.AlignCenter)
        layout.addWidget(ts)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _VuePleinEcran(QDialog):
    """Dialogue affichant le graphique en grand."""

    def __init__(self, pixmap: QPixmap, label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Graphique — {label}")
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Image en grand
        img_label = QLabel()
        scaled = pixmap.scaled(self.width() - 40, self.height() - 80,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img_label.setPixmap(scaled)
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(img_label)
        self._img_label = img_label
        self._pixmap = pixmap

        # Barre du bas
        bar = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
        bar.addWidget(lbl)
        bar.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.setStyleSheet("""
            QPushButton {
                background: #e74c3c; color: white; font-weight: bold;
                border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        btn_close.clicked.connect(self.close)
        bar.addWidget(btn_close)
        layout.addLayout(bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        scaled = self._pixmap.scaled(self.width() - 40, self.height() - 80,
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_label.setPixmap(scaled)


class HistoriqueTab(QWidget):
    """Onglet galerie : stocke les graphiques générés et les affiche en miniatures."""

    def __init__(self):
        super().__init__()
        self._entries = []  # list of (QPixmap_full, label, timestamp)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        layout.addWidget(titre("Historique des graphiques"))
        layout.addWidget(description(
            "Tous les graphiques générés pendant la session sont enregistrés ici. "
            "Cliquez sur une miniature pour l'afficher en grand."
        ))
        layout.addWidget(separateur())

        # Barre d'outils
        toolbar = QHBoxLayout()
        self._lbl_count = QLabel("0 graphique(s)")
        self._lbl_count.setStyleSheet(LABEL_STYLE)
        toolbar.addWidget(self._lbl_count)
        toolbar.addStretch()
        btn_clear = bouton("Vider l'historique", primary=False)
        btn_clear.clicked.connect(self._vider)
        toolbar.addWidget(btn_clear)
        layout.addLayout(toolbar)

        # Zone scrollable pour la grille de miniatures
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: #f5f6fa; }")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: #f5f6fa;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll, stretch=1)

    def ajouter_graphique(self, figure: Figure, label: str):
        """Capture une Figure matplotlib et l'ajoute à la galerie (évite doublons)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Éviter les doublons : même label dans la même seconde
        if self._entries:
            last_pixmap, last_label, last_ts = self._entries[-1]
            if last_label == label and last_ts == timestamp:
                return
        pixmap = self._figure_to_pixmap(figure)
        self._entries.append((pixmap, label, timestamp))
        self._rafraichir_grille()

    def _figure_to_pixmap(self, fig: Figure) -> QPixmap:
        """Convertit une Figure matplotlib en QPixmap sans détacher le canvas original."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

    def _rafraichir_grille(self):
        """Reconstruit la grille de miniatures."""
        # Nettoyer
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = 4
        for idx, (pixmap, label, ts) in enumerate(self._entries):
            row = idx // cols
            col = idx % cols
            mini = _Miniature(pixmap, label, ts)
            mini.clicked.connect(lambda px=pixmap, lbl=label: self._afficher_grand(px, lbl))
            self._grid_layout.addWidget(mini, row, col)

        self._lbl_count.setText(f"{len(self._entries)} graphique(s)")

    def _afficher_grand(self, pixmap: QPixmap, label: str):
        """Ouvre le dialogue plein écran pour un graphique."""
        dlg = _VuePleinEcran(pixmap, label, parent=self)
        dlg.exec_()

    def _vider(self):
        self._entries.clear()
        self._rafraichir_grille()
