APP          := ecoibeu-mouse
VERSION      := 1.0.0
ARCH         ?= x86_64
BUILD_DIR    := build
APPDIR       := $(BUILD_DIR)/$(APP).AppDir
OUTPUT       := $(APP)-$(ARCH).AppImage
APPIMAGETOOL := ./appimagetool-x86_64.AppImage

PREFIX       ?= $(HOME)/.local
BINDIR       := $(PREFIX)/bin
APPSDIR      := $(PREFIX)/share/applications
ICONSDIR     := $(PREFIX)/share/icons/hicolor
INSTALLED_APP     := $(BINDIR)/$(APP).AppImage
INSTALLED_DESKTOP := $(APPSDIR)/$(APP).desktop

SOURCES      := app.py wkpc_protocol.py apply_helper.py key_catalog.py
ICON_SIZES   := 16 24 32 48 64 128 256
ICONS        := $(addprefix packaging/icons/,$(addsuffix .png,$(ICON_SIZES)))
ICON_STAMP   := packaging/icons/.stamp

.PHONY: all appimage appdir check icons install uninstall run clean distclean

all: appimage

appimage: $(OUTPUT)

check:
	/usr/bin/python3 -m py_compile $(SOURCES)
	/usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "3.0")' \
		|| { echo "Falta PyGObject/GTK3 para /usr/bin/python3"; exit 1; }
	@echo "OK: fontes compilam e GTK3 está disponível"

icons:
	/usr/bin/python3 packaging/render-icons.py
	touch "$(ICON_STAMP)"

appdir: $(APPDIR)/.DirIcon

$(ICON_STAMP): packaging/ecoibeu-mouse.svg packaging/render-icons.py
	/usr/bin/python3 packaging/render-icons.py
	touch "$@"

$(ICONS): $(ICON_STAMP)

$(APPDIR)/.DirIcon: $(SOURCES) packaging/AppRun packaging/ecoibeu-mouse \
                    packaging/ecoibeu-mouse.desktop packaging/ecoibeu-mouse.svg \
                    $(ICONS) $(ICON_STAMP)
	rm -rf "$(APPDIR)"
	mkdir -p "$(APPDIR)/usr/bin" "$(APPDIR)/usr/share/$(APP)"
	mkdir -p "$(APPDIR)/usr/share/applications"
	mkdir -p "$(APPDIR)/usr/share/icons/hicolor/scalable/apps"

	install -m 755 packaging/AppRun "$(APPDIR)/AppRun"
	install -m 755 packaging/ecoibeu-mouse "$(APPDIR)/usr/bin/$(APP)"
	install -m 644 packaging/ecoibeu-mouse.desktop "$(APPDIR)/$(APP).desktop"
	install -m 644 packaging/ecoibeu-mouse.desktop \
		"$(APPDIR)/usr/share/applications/$(APP).desktop"

	for src in $(SOURCES); do \
		install -m 644 "$$src" "$(APPDIR)/usr/share/$(APP)/$$src"; \
	done

	for size in $(ICON_SIZES); do \
		dir="$(APPDIR)/usr/share/icons/hicolor/$${size}x$${size}/apps"; \
		mkdir -p "$$dir"; \
		install -m 644 "packaging/icons/$$size.png" "$$dir/$(APP).png"; \
	done

	install -m 644 packaging/ecoibeu-mouse.svg \
		"$(APPDIR)/usr/share/icons/hicolor/scalable/apps/$(APP).svg"
	install -m 644 packaging/icons/256.png "$(APPDIR)/$(APP).png"
	ln -sf "$(APP).png" "$(APPDIR)/.DirIcon"

$(OUTPUT): $(APPDIR)/.DirIcon
	rm -f "$@"
	ARCH=$(ARCH) VERSION=$(VERSION) APPIMAGE_EXTRACT_AND_RUN=1 \
		$(APPIMAGETOOL) --no-appstream "$(APPDIR)" "$@"
	@echo "Gerado: $(OUTPUT)"

# Integra no app grid do usuário (GNOME/Ubuntu) sem precisar de AppImageLauncher.
install: $(OUTPUT)
	install -d "$(BINDIR)" "$(APPSDIR)" "$(ICONSDIR)"
	install -m 755 "$(OUTPUT)" "$(INSTALLED_APP)"
	sed 's|@EXEC@|$(INSTALLED_APP)|g' \
		packaging/ecoibeu-mouse.desktop.in > "$(INSTALLED_DESKTOP)"
	chmod 644 "$(INSTALLED_DESKTOP)"
	for size in $(ICON_SIZES); do \
		dir="$(ICONSDIR)/$${size}x$${size}/apps"; \
		install -d "$$dir"; \
		install -m 644 "packaging/icons/$$size.png" "$$dir/$(APP).png"; \
	done
	install -d "$(ICONSDIR)/scalable/apps"
	install -m 644 packaging/ecoibeu-mouse.svg \
		"$(ICONSDIR)/scalable/apps/$(APP).svg"
	-update-desktop-database "$(APPSDIR)" >/dev/null 2>&1 || true
	-gtk-update-icon-cache -f -t "$(ICONSDIR)" >/dev/null 2>&1 || true
	@echo "Instalado: $(INSTALLED_APP)"
	@echo "Procure por \"ecoibeu mouse\" no app grid."

uninstall:
	rm -f "$(INSTALLED_APP)" "$(INSTALLED_DESKTOP)"
	rm -f "$(ICONSDIR)"/*/apps/$(APP).png
	rm -f "$(ICONSDIR)/scalable/apps/$(APP).svg"
	-update-desktop-database "$(APPSDIR)" >/dev/null 2>&1 || true
	-gtk-update-icon-cache -f -t "$(ICONSDIR)" >/dev/null 2>&1 || true
	@echo "ecoibeu mouse removido do app grid."

run:
	DISPLAY=$${DISPLAY:-:0} ./run.sh

clean:
	rm -rf "$(BUILD_DIR)" "$(OUTPUT)"

distclean: clean
	rm -rf __pycache__
