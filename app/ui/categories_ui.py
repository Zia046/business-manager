"""New Account > Categories: see, add and delete product categories."""
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from ..services import masters
from ..services.common import BusinessError
from .widgets import make_table, selected_id, set_row


class CategoriesDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Categories")
        self.resize(520, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Every product must belong to a category. Products in the "
                             "<b>Mobile Phone</b> category need IMEI numbers."))
        row = QHBoxLayout()
        self.name = QLineEdit(placeholderText="New category name")
        self.name.returnPressed.connect(self.add)
        add = QPushButton("Add Category")
        add.setAutoDefault(False)
        add.clicked.connect(self.add)
        row.addWidget(self.name, 1)
        row.addWidget(add)
        lay.addLayout(row)
        self.table = make_table(["ID", "Category", "Type", "Products"])
        lay.addWidget(self.table)
        buttons = QHBoxLayout()
        delete = QPushButton("Delete Selected")
        delete.setObjectName("secondary")
        delete.setAutoDefault(False)
        delete.clicked.connect(self.delete)
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        buttons.addWidget(delete)
        buttons.addStretch()
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        self.reload()

    def reload(self):
        rows = masters.list_categories(self.db)
        self.table.setRowCount(len(rows))
        for i, c in enumerate(rows):
            used = self.db.scalar("SELECT COUNT(*) FROM products WHERE category=? COLLATE NOCASE", (c["name"],))
            kind = "Phones (IMEI)" if c["is_mobile"] else ("Built-in" if c["is_system"] else "")
            set_row(self.table, i, [c["id"], c["name"], kind, used], (3,))

    def add(self):
        self.error.setText("")
        try:
            masters.add_category(self.db, self.name.text())
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.name.clear()
        self.reload()

    def delete(self):
        self.error.setText("")
        cid = selected_id(self.table)
        if cid is None:
            self.error.setText("Select a category first.")
            return
        if QMessageBox.question(self, "Delete category", "Delete this category?") != QMessageBox.Yes:
            return
        try:
            masters.delete_category(self.db, cid)
        except BusinessError as exc:
            self.error.setText(str(exc))
            return
        self.reload()
