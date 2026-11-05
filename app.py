#!/usr/bin/python3
"""ecoibeu mouse - perfis de botões para o WKPC-S44 / EVISION.

Interface GTK3. A gravação no mouse é feita por apply_helper.py, executado
como root via `sudo -A` com um askpass que chama o zenity.
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from key_catalog import BY_NAME, BY_VALUE, CATALOG, ensure_value  # noqa: E402

APP_ID = "br.ecoibeu.mouseprofiles"
PROGRAM_NAME = "ecoibeu-mouse"

# No Wayland o app_id da janela vem de g_get_prgname(), não do application_id
# do Gtk.Application. Sem isso o app anuncia "app.py" e o GNOME não encontra
# o .desktop correspondente (dock sem ícone). O program class também define o
# WM_CLASS no X11, que é o que o StartupWMClass usa.
GLib.set_prgname(PROGRAM_NAME)
Gdk.set_program_class(PROGRAM_NAME)

APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "ecoibeu-mouse")
PROFILES_FILE = os.path.join(CONFIG_DIR, "profiles.json")
DATA_DIR = os.path.join(GLib.get_user_data_dir(), "ecoibeu-mouse")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "ecoibeu-mouse")

DEFAULT_FORWARD = 0x200200  # Shift esquerdo
DEFAULT_BACK = 0x200400     # Alt esquerdo


def icon_file():
    """Acha o ícone tanto rodando do fonte quanto de dentro do AppImage."""
    candidates = (
        os.path.join(APP_DIR, "packaging", "icons", "256.png"),
        os.path.join(APP_DIR, os.pardir, "icons", "hicolor", "256x256",
                     "apps", "ecoibeu-mouse.png"),
        os.path.join(APP_DIR, os.pardir, "..", "ecoibeu-mouse.png"),
    )
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return None


# ---------------------------------------------------------------------------
# Persistência dos perfis (ficam no PC, não no mouse)
# ---------------------------------------------------------------------------

def default_profiles():
    return [{
        "id": uuid.uuid4().hex,
        "name": "Perfil 1",
        "forward": DEFAULT_FORWARD,
        "back": DEFAULT_BACK,
    }]


def load_state():
    """Carrega perfis + id do perfil padrão."""
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        profiles = raw.get("profiles", [])
        clean = []
        for item in profiles:
            if not isinstance(item, dict):
                continue
            try:
                clean.append({
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "name": str(item.get("name") or "Perfil"),
                    "forward": int(item.get("forward", DEFAULT_FORWARD)),
                    "back": int(item.get("back", DEFAULT_BACK)),
                })
            except (TypeError, ValueError):
                continue
        if not clean:
            clean = default_profiles()
        default_id = str(raw.get("default_id") or "")
        if default_id not in {item["id"] for item in clean}:
            default_id = clean[0]["id"]
        return clean, default_id
    except (OSError, ValueError):
        profiles = default_profiles()
        return profiles, profiles[0]["id"]


def save_state(profiles, default_id):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = PROFILES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"profiles": profiles, "default_id": default_id},
                  handle, indent=2, ensure_ascii=False)
    os.replace(tmp, PROFILES_FILE)


def save_backup(result):
    data_hex = result.get("keymap_before_hex")
    if not data_hex:
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = time.strftime("keymap-%Y%m%d-%H%M%S-") + f"{time.time_ns() % 1000000:06d}.bin"
    path = os.path.join(BACKUP_DIR, name)
    with open(path, "wb") as handle:
        handle.write(bytes.fromhex(data_hex))
    return path


# ---------------------------------------------------------------------------
# Root via sudo + zenity
# ---------------------------------------------------------------------------

def ensure_askpass():
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "askpass.sh")
    content = (
        "#!/bin/sh\n"
        "exec zenity --password --title='Senha do sudo - ecoibeu mouse'\n"
    )
    if not os.path.exists(path) or open(path, encoding="utf-8").read() != content:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(path, 0o700)
    return path


HELPER_FILES = ("apply_helper.py", "wkpc_protocol.py")


def prepare_helper():
    """Copia o helper para fora do AppImage antes de rodar com sudo.

    O squashfs montado pelo AppImage só é acessível ao usuário que montou;
    o root do sudo recebe EACCES ao abrir arquivos dentro de /tmp/.mount_*.
    Copiamos os arquivos para o cache do usuário (root consegue ler com
    CAP_DAC_OVERRIDE) e executamos essa cópia.
    """
    target_dir = os.path.join(CACHE_DIR, "helper")
    os.makedirs(target_dir, exist_ok=True)
    os.chmod(target_dir, 0o755)

    for name in HELPER_FILES:
        source = os.path.join(APP_DIR, name)
        target = os.path.join(target_dir, name)
        with open(source, "rb") as handle:
            data = handle.read()
        try:
            with open(target, "rb") as handle:
                if handle.read() == data:
                    os.chmod(target, 0o644)
                    continue
        except OSError:
            pass

        tmp = target + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)

    return os.path.join(target_dir, "apply_helper.py")


def run_helper(forward_value, back_value):
    askpass = ensure_askpass()
    helper = prepare_helper()
    env = os.environ.copy()
    env["SUDO_ASKPASS"] = askpass
    if not env.get("DISPLAY") and os.path.exists("/tmp/.X11-unix/X0"):
        env["DISPLAY"] = ":0"

    command = [
        "sudo", "-A", "/usr/bin/python3", helper,
        "--forward", f"0x{forward_value:06X}",
        "--back", f"0x{back_value:06X}",
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, env=env, timeout=180)

    payload = None
    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue

    if payload is None:
        detail = completed.stderr.strip() or completed.stdout.strip()
        if completed.returncode == 1 and not detail:
            detail = "autorização cancelada ou falhou"
        raise RuntimeError(detail or f"helper terminou com código {completed.returncode}")

    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or "falha desconhecida")
    return payload


# ---------------------------------------------------------------------------
# Dropdown pesquisável de teclas
# ---------------------------------------------------------------------------

class KeyCombo:
    """Gtk.ComboBoxText com entrada de texto, autocomplete e busca."""

    def __init__(self, on_change):
        self.on_change = on_change
        self._guard = False
        self.widget = Gtk.ComboBoxText.new_with_entry()
        self.widget.set_hexpand(True)

        self._known_ids = set()
        for key in CATALOG:
            self._add_item(key)

        entry = self.widget.get_child()
        self._completion_model = Gtk.ListStore(str)
        for key in CATALOG:
            self._completion_model.append([key.name])

        completion = Gtk.EntryCompletion()
        completion.set_model(self._completion_model)
        completion.set_text_column(0)
        completion.set_minimum_key_length(1)
        completion.set_popup_completion(True)
        completion.set_inline_completion(True)
        completion.connect("match-selected", self._on_match)
        entry.set_completion(completion)

        entry.connect("activate", self._on_entry_activate)
        entry.connect("changed", self._on_entry_changed)
        self.widget.connect("changed", self._on_combo_changed)

    def _add_item(self, key):
        ident = f"{key.value:06x}"
        if ident in self._known_ids:
            return
        self.widget.append(ident, key.name)
        self._known_ids.add(ident)

    def _on_match(self, _completion, model, tree_iter):
        name = model[tree_iter][0]
        key = BY_NAME.get(name)
        if key is not None:
            self.set_value(key.value)
        return True

    def _on_entry_activate(self, entry):
        key = BY_NAME.get(entry.get_text().strip())
        if key is not None:
            self.set_value(key.value)
        return False

    def _on_entry_changed(self, entry):
        if self._guard:
            return
        key = BY_NAME.get(entry.get_text().strip())
        if key is not None and self.widget.get_active_id() != f"{key.value:06x}":
            self.set_value(key.value)

    def _on_combo_changed(self, _combo):
        if self._guard:
            return
        ident = self.widget.get_active_id()
        if ident is None:
            return
        try:
            value = int(ident, 16)
        except ValueError:
            return
        if self.on_change is not None:
            self.on_change(value)

    def set_value(self, value):
        key = ensure_value(value)
        if key.name not in self._completion_model_names():
            self._completion_model.append([key.name])
        self._add_item(key)

        ident = f"{value:06x}"
        if self.widget.get_active_id() == ident:
            return
        self._guard = True
        self.widget.set_active_id(ident)
        self._guard = False
        if self.on_change is not None:
            self.on_change(value)

    def _completion_model_names(self):
        return {row[0] for row in self._completion_model}

    def current_value(self, fallback):
        """Resolve o valor pelo texto exato; senão usa o item ativo."""
        key = BY_NAME.get(self.widget.get_child().get_text().strip())
        if key is not None:
            return key.value
        ident = self.widget.get_active_id()
        if ident is not None:
            try:
                return int(ident, 16)
            except ValueError:
                pass
        return fallback

    def set_sensitive(self, sensitive):
        self.widget.set_sensitive(sensitive)


# ---------------------------------------------------------------------------
# Card de perfil
# ---------------------------------------------------------------------------

class ProfileRow(Gtk.Frame):
    def __init__(self, app, data):
        super().__init__()
        self.app = app
        self.data = data
        self.set_shadow_type(Gtk.ShadowType.IN)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)
        outer.set_margin_start(12)
        outer.set_margin_end(12)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label="Nome do perfil:")
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(data.get("name", ""))
        self.name_entry.set_hexpand(True)
        self.name_entry.connect("changed", self._on_name_changed)

        self.default_button = Gtk.Button()
        self.default_button.set_relief(Gtk.ReliefStyle.NONE)
        self.default_button.connect(
            "clicked", lambda _b: self.app.set_default_profile(self))

        header.pack_start(name_label, False, False, 0)
        header.pack_start(self.name_entry, True, True, 0)
        header.pack_start(self.default_button, False, False, 0)
        outer.pack_start(header, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_hexpand(True)

        forward_label = Gtk.Label(label="Botão forward (entry 3):")
        forward_label.set_xalign(0)
        self.forward_combo = KeyCombo(
            lambda value: self._on_key_changed("forward", value))
        grid.attach(forward_label, 0, 0, 1, 1)
        grid.attach(self.forward_combo.widget, 1, 0, 1, 1)

        back_label = Gtk.Label(label="Botão back (entry 4):")
        back_label.set_xalign(0)
        self.back_combo = KeyCombo(
            lambda value: self._on_key_changed("back", value))
        grid.attach(back_label, 0, 1, 1, 1)
        grid.attach(self.back_combo.widget, 1, 1, 1, 1)
        outer.pack_start(grid, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.status_label.set_hexpand(True)
        self.status_label.set_line_wrap(True)
        self.status_label.get_style_context().add_class("dim-label")

        self.delete_button = Gtk.Button()
        self.delete_button.set_image(Gtk.Image.new_from_icon_name(
            "user-trash-symbolic", Gtk.IconSize.BUTTON))
        self.delete_button.set_tooltip_text("Apagar perfil")
        self.delete_button.get_style_context().add_class("destructive-action")
        self.delete_button.connect("clicked", lambda _b: self.app.delete_profile(self))

        self.apply_button = Gtk.Button()
        self.apply_button.set_image(Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON))
        self.apply_button.set_tooltip_text("Aplicar no mouse")
        self.apply_button.get_style_context().add_class("suggested-action")
        self.apply_button.connect("clicked", lambda _b: self.app.apply_profile(self))

        actions.pack_start(self.status_label, True, True, 0)
        actions.pack_start(self.delete_button, False, False, 0)
        actions.pack_start(self.apply_button, False, False, 0)
        outer.pack_start(actions, False, False, 0)

        # Mistura os valores salvos no catálogo antes de exibir.
        self.forward_combo.set_value(int(data.get("forward", DEFAULT_FORWARD)))
        self.back_combo.set_value(int(data.get("back", DEFAULT_BACK)))

    def _on_name_changed(self, entry):
        self.data["name"] = entry.get_text()
        self.app.persist()

    def _on_key_changed(self, field, value):
        self.data[field] = value
        self.app.persist()

    def set_is_default(self, is_default):
        icon = "starred-symbolic" if is_default else "non-starred-symbolic"
        self.default_button.set_image(
            Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        self.default_button.set_tooltip_text(
            "Perfil padrão" if is_default else "Definir como perfil padrão")

    def set_busy(self, busy):
        for widget in (self.name_entry, self.forward_combo, self.back_combo,
                       self.default_button, self.delete_button,
                       self.apply_button):
            widget.set_sensitive(not busy)
        if busy:
            self.set_status("Aplicando no mouse...")

    def set_status(self, text):
        self.status_label.set_text(text)

    def show_result(self, result):
        self.set_busy(False)
        backup = save_backup(result)
        device = result.get("device", "?")
        message = f"Aplicado em {device}."
        if backup:
            message += f" Backup: {backup}"
        self.set_status(message)


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------

class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.window = None
        self.profiles = []
        self.default_id = ""
        self.rows = []
        self.busy = False
        self.list_box = None
        self.empty_label = None
        self.default_apply_button = None

    def do_activate(self):
        if self.window is None:
            self.build_window()
        self.window.show_all()

    def build_window(self):
        self.profiles, self.default_id = load_state()

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("ecoibeu mouse")
        self.window.set_default_size(760, 560)
        self.window.set_icon_name(PROGRAM_NAME)
        path = icon_file()
        if path is not None:
            try:
                self.window.set_icon_from_file(path)
            except GLib.Error:
                pass

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "ecoibeu mouse"
        header.props.subtitle = "Perfis de botões do WKPC-S44"
        self.window.set_titlebar(header)

        new_button = Gtk.Button()
        new_button.set_image(Gtk.Image.new_from_icon_name(
            "list-add-symbolic", Gtk.IconSize.BUTTON))
        new_button.set_tooltip_text("Novo perfil")
        new_button.get_style_context().add_class("suggested-action")
        new_button.connect("clicked", lambda _b: self.new_profile())
        header.pack_end(new_button)

        self.default_apply_button = Gtk.Button()
        self.default_apply_button.set_image(Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON))
        self.default_apply_button.connect(
            "clicked", lambda _b: self.apply_default_profile())
        header.pack_end(self.default_apply_button)

        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.add(root_box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        root_box.pack_start(scrolled, True, True, 0)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.list_box.set_margin_top(6)
        self.list_box.set_margin_bottom(12)
        self.list_box.set_margin_start(12)
        self.list_box.set_margin_end(12)
        scrolled.add(self.list_box)

        self.empty_label = Gtk.Label(label="Nenhum perfil. Clique em “Novo perfil”.")
        self.empty_label.set_margin_top(40)
        self.empty_label.set_margin_bottom(40)
        self.empty_label.get_style_context().add_class("dim-label")
        self.empty_label.set_no_show_all(True)
        self.list_box.pack_start(self.empty_label, False, False, 0)

        for data in self.profiles:
            self.add_row(data)
        self.update_empty_state()
        self.refresh_defaults()

    def add_row(self, data):
        row = ProfileRow(self, data)
        self.rows.append(row)
        self.list_box.pack_start(row, False, False, 0)
        row.show_all()
        self.update_empty_state()

    def update_empty_state(self):
        if self.empty_label is not None:
            self.empty_label.set_visible(not self.rows)

    def default_row(self):
        for row in self.rows:
            if row.data.get("id") == self.default_id:
                return row
        return None

    def refresh_defaults(self):
        for row in self.rows:
            row.set_is_default(row.data.get("id") == self.default_id)
        if self.default_apply_button is None:
            return
        row = self.default_row()
        if row is None:
            self.default_apply_button.set_sensitive(False)
            self.default_apply_button.set_tooltip_text("Nenhum perfil padrão")
        else:
            self.default_apply_button.set_sensitive(not self.busy)
            name = row.data.get("name") or "perfil padrão"
            self.default_apply_button.set_tooltip_text(
                f"Aplicar perfil padrão: {name}")

    def persist(self):
        try:
            save_state(self.profiles, self.default_id)
        except OSError as exc:
            self.show_error(f"Não foi possível salvar os perfis: {exc}")

    def new_profile(self):
        used = {profile.get("name", "") for profile in self.profiles}
        number = 1
        while f"Perfil {number}" in used:
            number += 1
        data = {
            "id": uuid.uuid4().hex,
            "name": f"Perfil {number}",
            "forward": DEFAULT_FORWARD,
            "back": DEFAULT_BACK,
        }
        self.profiles.append(data)
        if not self.default_id or self.default_row() is None:
            self.default_id = data["id"]
        self.persist()
        self.add_row(data)
        self.window.show_all()
        self.update_empty_state()
        self.refresh_defaults()

    def set_default_profile(self, row):
        ident = row.data.get("id")
        if not ident:
            return
        self.default_id = ident
        self.persist()
        self.refresh_defaults()

    def apply_default_profile(self):
        row = self.default_row()
        if row is None:
            self.show_error("Nenhum perfil padrão definido.")
            return
        self.apply_profile(row)

    def delete_profile(self, row):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Apagar o perfil “{row.data.get('name', '')}”?",
        )
        dialog.format_secondary_text(
            "Isso remove apenas o perfil salvo no computador. "
            "O mouse não é alterado.")
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return

        if row.data in self.profiles:
            self.profiles.remove(row.data)
        if row in self.rows:
            self.rows.remove(row)
        row.destroy()
        if self.default_id == row.data.get("id"):
            self.default_id = self.profiles[0]["id"] if self.profiles else ""
        self.persist()
        self.update_empty_state()
        self.refresh_defaults()

    def apply_profile(self, row):
        if self.busy:
            self.show_error("Já existe uma aplicação em andamento.")
            return
        self.busy = True
        row.set_busy(True)
        self.refresh_defaults()
        forward_value = row.forward_combo.current_value(
            int(row.data.get("forward", DEFAULT_FORWARD)))
        back_value = row.back_combo.current_value(
            int(row.data.get("back", DEFAULT_BACK)))
        row.data["forward"] = forward_value
        row.data["back"] = back_value
        self.persist()

        def worker():
            try:
                result = run_helper(forward_value, back_value)
                GLib.idle_add(self.apply_finished, row, result, None)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.apply_finished, row, None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def apply_finished(self, row, result, error):
        self.busy = False
        row.set_busy(False)
        self.refresh_defaults()
        if error is not None:
            self.show_error(error)
            row.set_status("Falhou. Veja a mensagem de erro.")
            return False
        row.show_result(result)
        return False

    def show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Erro ao aplicar o perfil",
        )
        dialog.format_secondary_text(str(message))
        dialog.run()
        dialog.destroy()


def main():
    app = App()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
