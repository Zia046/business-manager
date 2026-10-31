"""Utilities > Backup and Restore Backup screens."""
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from ..services import backup
from ..services.common import BusinessError
from .widgets import make_table, set_row


class BackupDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Backup")
        self.resize(760, 560)
        s = backup.get_settings(db.data_dir)
        lay = QVBoxLayout(self)

        info = QLabel(f"Backups are saved (encrypted) in:\n{backup.backups_dir(db.data_dir)}")
        info.setObjectName("subtitle")
        lay.addWidget(info)
        row = QHBoxLayout()
        now = QPushButton("Backup Now")
        now.clicked.connect(self.backup_now)
        other = QPushButton("Backup to USB / Other Folder...")
        other.setObjectName("secondary")
        other.clicked.connect(self.backup_elsewhere)
        row.addWidget(now)
        row.addWidget(other)
        row.addStretch()
        lay.addLayout(row)

        self.auto = QCheckBox("Automatic backup every time the program is closed (keeps the last 30)")
        self.auto.setChecked(s["auto_backup"])
        self.auto.toggled.connect(self.save_settings)
        lay.addWidget(self.auto)
        erow = QHBoxLayout()
        erow.addWidget(QLabel("Also copy automatic backups to:"))
        self.extra = QLineEdit(s["extra_folder"], placeholderText="e.g. E:\\Backups  (USB drive) - optional")
        self.extra.editingFinished.connect(self.save_settings)
        pick = QPushButton("Choose...")
        pick.setObjectName("secondary")
        pick.clicked.connect(self.choose_extra)
        erow.addWidget(self.extra, 1)
        erow.addWidget(pick)
        lay.addLayout(erow)

        lay.addWidget(QLabel("Existing backups:"))
        self.table = make_table(["File", "Date", "Size (KB)"], stretch_col=0)
        lay.addWidget(self.table)
        self.msg = QLabel()
        lay.addWidget(self.msg)
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.reload()

    def reload(self):
        rows = backup.list_backups(self.db.data_dir)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            set_row(self.table, i, [r["name"], r["time"], r["size_kb"]], (2,))

    def save_settings(self, *_):
        backup.save_settings(self.db.data_dir, auto_backup=self.auto.isChecked(),
                             extra_folder=self.extra.text().strip())

    def choose_extra(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder (e.g. USB drive)")
        if d:
            self.extra.setText(d)
            self.save_settings()

    def _run(self, dest=None):
        try:
            out = backup.create_backup(self.db, dest)
        except Exception as exc:
            QMessageBox.warning(self, "Backup failed", f"Could not create the backup:\n{exc}")
            return
        self.msg.setText(f"Backup saved: {out}")
        self.reload()

    def backup_now(self):
        self._run()

    def backup_elsewhere(self):
        d = QFileDialog.getExistingDirectory(self, "Choose where to save the backup (e.g. USB drive)")
        if d:
            self._run(d)


def restore_dialog(win):
    """Pick a backup (from the list folder or any file), confirm, restore, then close the program."""
    db = win.db
    path, _ = QFileDialog.getOpenFileName(win, "Select backup file", str(backup.backups_dir(db.data_dir)),
                                          f"Business Manager backup (*{backup.EXT})")
    if not path:
        return
    try:
        backup.validate_backup(path)
    except BusinessError as exc:
        QMessageBox.warning(win, "Restore", str(exc))
        return
    if QMessageBox.warning(
            win, "Restore backup",
            f"Restore this backup?\n\n{Path(path).name}\n\nAll data entered AFTER this backup was made will be "
            "replaced. A safety copy of your current data is saved first.\n\nThe program will close; open it "
            "again and log in with the password that was used when the backup was made.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
        return
    try:
        safety = backup.restore_backup(db, path)
    except BusinessError as exc:
        QMessageBox.warning(win, "Restore failed", str(exc))
        return
    except Exception as exc:
        QMessageBox.critical(win, "Restore failed", f"Restore failed:\n{exc}\n\nYour previous data was not changed "
                                                    "if the safety backup exists in the backups folder.")
        return
    QMessageBox.information(win, "Restore complete",
                            f"Backup restored.\nSafety copy of the old data: {safety.name}\n\nThe program will now close.")
    win.skip_exit_backup = True       # do not overwrite/mix: the restored data is what we want to keep
    QApplication.quit()
