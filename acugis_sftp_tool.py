import os
import json
import paramiko
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QInputDialog, QProgressDialog, QLineEdit, QComboBox, QDialog, QVBoxLayout, QLabel, QFormLayout, QPushButton, QHBoxLayout
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject
from qgis.utils import iface

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".sftp_uploader_config.json")

class AcugisSFTPTool:
    def __init__(self, iface):
        self.iface = iface
        self.upload_action = None
        self.config_action = None

    def initGui(self):
        plugin_dir = os.path.dirname(__file__)
        icon_path = os.path.join(plugin_dir, 'icon.png')
        config_icon_path = os.path.join(plugin_dir, 'icon_configure.png') if os.path.exists(os.path.join(plugin_dir, 'icon_configure.png')) else icon_path

        self.upload_action = QAction(QIcon(icon_path), "Upload Project Directory via SFTP", self.iface.mainWindow())
        self.upload_action.triggered.connect(self.upload_project_directory_via_sftp)
        self.iface.addToolBarIcon(self.upload_action)
        self.iface.addPluginToMenu("&AcuGIS SFTP", self.upload_action)

        self.config_action = QAction(QIcon(config_icon_path), "Configure SFTP Servers", self.iface.mainWindow())
        self.config_action.triggered.connect(self.configure_servers)
        self.iface.addToolBarIcon(self.config_action)
        self.iface.addPluginToMenu("&AcuGIS SFTP", self.config_action)

    def unload(self):
        self.iface.removePluginMenu("&AcuGIS SFTP", self.upload_action)
        self.iface.removeToolBarIcon(self.upload_action)
        self.iface.removePluginMenu("&AcuGIS SFTP", self.config_action)
        self.iface.removeToolBarIcon(self.config_action)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    def save_config(self, config):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

    def configure_servers(self):
        from qgis.PyQt.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QVBoxLayout, QLineEdit, QLabel, QListWidget, QPushButton, QHBoxLayout

        class ConfigDialog(QDialog):
            def __init__(self, config):
                super().__init__()
                self.setWindowTitle("Configure SFTP Servers")
                self.config = config
                self.layout = QVBoxLayout()

                # Add logo and branding
                logo_label = QLabel()
                logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
                if os.path.exists(logo_path):
                    logo_label.setPixmap(QIcon(logo_path).pixmap(120, 40))
                branding_label = QLabel("<b style='font-size:14pt;'>AcuGIS Plugin</b><br><span style='font-size:10pt;'>Secure SFTP Deployment Tool</span>")
                branding_label.setAlignment(Qt.AlignCenter)

                self.layout.addWidget(logo_label)
                self.layout.addWidget(branding_label)

                self.list_widget = QListWidget()
                self.list_widget.addItems(sorted(config.keys()))
                self.layout.addWidget(self.list_widget)

                self.form_layout = QFormLayout()
                self.server_name = QLineEdit()
                self.host = QLineEdit()
                self.username = QLineEdit()
                self.password = QLineEdit()
                self.password.setEchoMode(QLineEdit.Password)
                self.port = QLineEdit()

                self.form_layout.addRow("Server Name:", self.server_name)
                self.form_layout.addRow("Host:", self.host)
                self.form_layout.addRow("Username:", self.username)
                self.form_layout.addRow("Password:", self.password)
                self.form_layout.addRow("Port (default 3839):", self.port)

                self.layout.addLayout(self.form_layout)

                self.button_layout = QHBoxLayout()
                self.save_button = QPushButton("Save")
                self.delete_button = QPushButton("Delete")
                self.test_button = QPushButton("Test Connection")
                self.button_layout.addWidget(self.save_button)
                self.button_layout.addWidget(self.delete_button)
                self.button_layout.addWidget(self.test_button)

                self.layout.addLayout(self.button_layout)
                self.setLayout(self.layout)

                self.list_widget.currentItemChanged.connect(self.load_selected)
                self.save_button.clicked.connect(self.save_entry)
                self.delete_button.clicked.connect(self.delete_entry)
                self.test_button.clicked.connect(self.test_connection)

            def load_selected(self):
                name = self.list_widget.currentItem().text()
                entry = self.config.get(name, {})
                self.server_name.setText(name)
                self.host.setText(entry.get('host', ''))
                self.username.setText(entry.get('username', ''))
                self.password.setText(entry.get('password', ''))
                self.port.setText(str(entry.get('port', '3839')))

            def save_entry(self):
                name = self.server_name.text().strip()
                if not name:
                    QMessageBox.warning(self, "Error", "Server name is required.")
                    return
                self.config[name] = {
                    'host': self.host.text().strip(),
                    'username': self.username.text().strip(),
                    'password': self.password.text().strip(),
                    'port': int(self.port.text().strip()) if self.port.text().strip().isdigit() else 3839
                }
                if name not in [self.list_widget.item(i).text() for i in range(self.list_widget.count())]:
                    self.list_widget.addItem(name)
                QMessageBox.information(self, "Saved", f"Server '{name}' saved.")

            def delete_entry(self):
                name = self.server_name.text().strip()
                if name in self.config:
                    confirm = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to delete server '{name}'?", QMessageBox.Yes | QMessageBox.No)
                    if confirm != QMessageBox.Yes:
                        return
                    del self.config[name]
                    items = self.list_widget.findItems(name, Qt.MatchExactly)
                    for item in items:
                        self.list_widget.takeItem(self.list_widget.row(item))
                    self.server_name.clear()
                    self.host.clear()
                    self.username.clear()
                    self.password.clear()
                    self.port.clear()
                    self.accept()  # Ensure dialog returns accepted state so config is saved
                    QMessageBox.information(self, "Deleted", f"Server '{name}' deleted.")

            def test_connection(self):
                host = self.host.text().strip()
                username = self.username.text().strip()
                password = self.password.text().strip()
                port = int(self.port.text().strip()) if self.port.text().strip().isdigit() else 3839
                try:
                    transport = paramiko.Transport((host, port))
                    transport.connect(username=username, password=password)
                    sftp = paramiko.SFTPClient.from_transport(transport)
                    sftp.close()
                    transport.close()
                    QMessageBox.information(self, "Success", "Connection successful!")
                except Exception as e:
                    QMessageBox.critical(self, "Connection Failed", f"Could not connect: {str(e)}")

        config = self.load_config()
        dlg = ConfigDialog(config)
        if dlg.exec_():
            self.save_config(config)

    from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel

    from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QFormLayout, QHBoxLayout

    def upload_project_directory_via_sftp(self):
        config = self.load_config()
        if not config:
            QMessageBox.warning(None, "No Servers Configured", "Please configure at least one SFTP server first.")
            return

        # Custom upload dialog
        upload_dialog = QDialog()
        upload_dialog.setWindowTitle("Upload Project Directory via SFTP")
        layout = QVBoxLayout()

        logo_label = QLabel()
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(logo_path):
            logo_label.setPixmap(QIcon(logo_path).pixmap(120, 40))
        branding_label = QLabel("<b style='font-size:14pt;'>AcuGIS Plugin</b><br><span style='font-size:10pt;'>Secure SFTP Deployment Tool</span>")
        branding_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(logo_label)
        layout.addWidget(branding_label)

        form_layout = QFormLayout()
        server_dropdown = QComboBox()
        server_names = list(config.keys())
        server_dropdown.addItems(server_names)
        remote_path_input = QLineEdit()

        form_layout.addRow("Select Server:", server_dropdown)
        form_layout.addRow("Remote Path:", remote_path_input)
        layout.addLayout(form_layout)

        test_button = QPushButton("Test Connection")
        layout.addWidget(test_button)

        button_box = QHBoxLayout()
        upload_btn = QPushButton("Upload")
        cancel_btn = QPushButton("Cancel")
        button_box.addWidget(upload_btn)
        button_box.addWidget(cancel_btn)
        layout.addLayout(button_box)

        upload_dialog.setLayout(layout)

        def test_connection():
            server_name = server_dropdown.currentText()
            if not server_name:
                QMessageBox.warning(upload_dialog, "Missing Server", "Please select a server to test.")
                return
            server_info = config.get(server_name, {})
            try:
                transport = paramiko.Transport((server_info['host'], server_info['port']))
                transport.connect(username=server_info['username'], password=server_info['password'])
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.close()
                transport.close()
                QMessageBox.information(upload_dialog, "Success", f"Connection to '{server_name}' successful!")
            except Exception as e:
                QMessageBox.critical(upload_dialog, "Connection Failed", f"Failed to connect to '{server_name}': {str(e)}")

        test_button.clicked.connect(test_connection)

        def start_upload():
            upload_dialog.accept()

        upload_btn.clicked.connect(start_upload)
        cancel_btn.clicked.connect(upload_dialog.reject)

        if not upload_dialog.exec_():
            return

        server_name = server_dropdown.currentText()
        remote_base_path = remote_path_input.text().strip()

        if not server_name or not remote_base_path:
            QMessageBox.warning(None, "Missing Info", "Please select a server and enter a remote path.")
            return

        server_info = config[server_name]

        project = QgsProject.instance()
        project_path = project.fileName()
        if not project_path:
            QMessageBox.warning(None, "No Project", "Please save the QGIS project first.")
            return

        project_dir = os.path.dirname(project_path)

        try:
            transport = paramiko.Transport((server_info['host'], server_info['port']))
            transport.connect(username=server_info['username'], password=server_info['password'])
            sftp = paramiko.SFTPClient.from_transport(transport)

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(server_info['host'], port=server_info['port'], username=server_info['username'], password=server_info['password'])

            file_list = []
            for root, _, files in os.walk(project_dir):
                for file in files:
                    local_path = os.path.join(root, file)
                    relative_path = os.path.relpath(local_path, project_dir)
                    remote_path = os.path.join(remote_base_path, relative_path).replace('\\', '/')
                    file_list.append((local_path, remote_path))

            progress = QProgressDialog("Uploading files...", "Cancel", 0, len(file_list))
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(True)
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(0)
            progress.setWindowTitle("SFTP Upload Progress")
            progress.setWindowModality(True)

            yes_to_all = False
            for i, (local_path, remote_path) in enumerate(file_list):
                if progress.wasCanceled():
                    break

                progress.setValue(i)
                progress.setLabelText(f"Uploading ({i + 1}/{len(file_list)}): {os.path.basename(local_path)}")
                progress.setLabelText(f"Uploading: {os.path.basename(local_path)}")

                upload_logs = []

                try:
                    skip_file = False
                    try:
                        remote_attr = sftp.stat(remote_path)
                        local_mtime = os.path.getmtime(local_path)
                        if int(local_mtime) <= int(remote_attr.st_mtime):
                            skip_file = True
                    except IOError:
                        pass

                    if skip_file and not yes_to_all:
                        overwrite = QMessageBox.question(None, "File Exists", f"{os.path.basename(local_path)} already exists on the server. Overwrite?", QMessageBox.Yes | QMessageBox.No | QMessageBox.YesToAll)
                        if overwrite == QMessageBox.No:
                            continue
                        elif overwrite == QMessageBox.YesToAll:
                            yes_to_all = True

                    remote_dir = os.path.dirname(remote_path)
                    dirs = remote_dir.strip('/').split('/')
                    path_so_far = ''
                    for dir in dirs:
                        path_so_far = f"{path_so_far}/{dir}" if path_so_far else f"/{dir}"
                        try:
                            sftp.listdir(path_so_far)
                        except IOError:
                            sftp.mkdir(path_so_far)

                    sftp.put(local_path, remote_path)
                    upload_logs.append(f"Uploaded: {local_path} → {remote_path}")
                    ssh.exec_command(f"sudo chown www-data:www-data '{remote_path}'")

                except Exception as upload_error:
                    log_message = f"Failed to upload {local_path}: {upload_error}"
                    upload_logs.append(log_message)
                    print(log_message)

            progress.setValue(len(file_list))
            sftp.close()
            ssh.close()
            transport.close()

            QMessageBox.information(None, "Upload Complete", "Project directory uploaded successfully via SFTP. Click OK to view the upload log.")

            # Show log dialog
            log_dialog = QDialog()
            log_dialog.setWindowTitle("Upload Log")
            log_layout = QVBoxLayout()
            log_label = QLabel("<b>Upload Log:</b>")
            log_layout.addWidget(log_label)

            from qgis.PyQt.QtWidgets import QTextEdit
            log_output = QTextEdit()
            log_output.setReadOnly(True)
            log_output.setText("\n".join(upload_logs))
            log_layout.addWidget(log_output)

            close_button = QPushButton("Close")
            close_button.clicked.connect(log_dialog.accept)
            log_layout.addWidget(close_button)

            log_dialog.setLayout(log_layout)
            log_dialog.exec_()

        except Exception as e:
            QMessageBox.critical(None, "Upload Failed", f"An error occurred: {str(e)}")

def classFactory(iface):
    return AcugisSFTPTool(iface)
