"""Catálogo de teclas do WKPC-S44 / EVISION.

A tabela foi extraída do executável do fabricante
(app/WKPC-S44 MOUSE.exe, offset de arquivo 0x2d2e38).

Cada entrada tem 6 bytes:

    VK  (2 bytes, little-endian)
    valor de atribuição (3 bytes, big-endian)
    padding (1 byte)

O valor de atribuição do teclado é 0x20 MM UU, onde MM é a máscara de
modificadores e UU é o HID keyboard usage.  Ex.: Shift esquerdo = 0x200200,
Alt esquerdo = 0x200400, tecla A = 0x200004.
"""

from collections import namedtuple

Key = namedtuple("Key", "name value")

# 91 entradas da tabela estática do fabricante (546 bytes).
_TABLE_HEX = (
    "a20020010000a00020020000a400200400005b0020080000a30020100000"
    "a10020200000a500204000005c0020800000410020000400420020000500"
    "430020000600440020000700450020000800460020000900470020000a00"
    "480020000b00490020000c004a0020000d004b0020000e004c0020000f00"
    "4d00200010004e00200011004f0020001200500020001300510020001400"
    "520020001500530020001600540020001700550020001800560020001900"
    "570020001a00580020001b00590020001c005a0020001d00310020001e00"
    "320020001f00330020002000340020002100350020002200360020002300"
    "3700200024003800200025003900200026003000200027000d0020002800"
    "1b0020002900080020002a00090020002b00200020002c00bd0020002d00"
    "bb0020002e00db0020002f00dd0020003000dc0020003100ba0020003300"
    "de0020003400c00020003500bc0020003600be0020003700bf0020003800"
    "140020003900700020003a00710020003b00720020003c00730020003d00"
    "740020003e00750020003f00760020004000770020004100780020004200"
    "7900200043007a00200044007b00200045002c0020004600910020004700"
    "1300200048002d0020004900240020004a00210020004b002e0020004c00"
    "230020004d00220020004e00270020004f00250020005000280020005100"
    "2600200052009000200053006f00200054006a00200055006d0020005600"
    "6b0020005700"
)

# VK (Windows) -> nome exibido na interface.
_VK_NAMES = {
    0xA2: "Ctrl esquerdo",
    0xA0: "Shift esquerdo",
    0xA4: "Alt esquerdo",
    0x5B: "Super esquerdo",
    0xA3: "Ctrl direito",
    0xA1: "Shift direito",
    0xA5: "Alt direito",
    0x5C: "Super direito",
    0x0D: "Enter",
    0x1B: "Esc",
    0x08: "Backspace",
    0x09: "Tab",
    0x20: "Espaço",
    0xBD: "Hífen (-)",
    0xBB: "Igual (=)",
    0xDB: "Colchete esquerdo ([)",
    0xDD: "Colchete direito (])",
    0xDC: "Barra invertida (\\)",
    0xBA: "Ponto e vírgula (;)",
    0xDE: "Aspas (')",
    0xC0: "Crase (`)",
    0xBC: "Vírgula (,)",
    0xBE: "Ponto (.)",
    0xBF: "Barra (/)",
    0x14: "Caps Lock",
    0x2C: "Print Screen",
    0x91: "Scroll Lock",
    0x13: "Pause",
    0x2D: "Insert",
    0x24: "Home",
    0x21: "Page Up",
    0x2E: "Delete",
    0x23: "End",
    0x22: "Page Down",
    0x27: "Seta direita",
    0x25: "Seta esquerda",
    0x28: "Seta baixo",
    0x26: "Seta cima",
    0x90: "Num Lock",
    0x6F: "Numérico /",
    0x6A: "Numérico *",
    0x6D: "Numérico -",
    0x6B: "Numérico +",
}

for _i in range(12):
    _VK_NAMES[0x70 + _i] = f"F{_i + 1}"

# O fabricante também aceita botões do mouse e "desativado".
_EXTRA = [
    (0x100100, "Mouse: botão esquerdo"),
    (0x100200, "Mouse: botão direito"),
    (0x100400, "Mouse: botão do meio"),
    (0x100800, "Mouse: voltar"),
    (0x101000, "Mouse: avançar"),
    (0xA00000, "Desativado"),
]


def _build_catalog():
    items = []
    blob = bytes.fromhex(_TABLE_HEX)
    for off in range(0, len(blob), 6):
        vk = int.from_bytes(blob[off:off + 2], "little")
        value = int.from_bytes(blob[off + 2:off + 5], "big")
        if 0x41 <= vk <= 0x5A:
            name = chr(vk)
        elif 0x30 <= vk <= 0x39:
            name = chr(vk)
        else:
            name = _VK_NAMES.get(vk, f"VK 0x{vk:02X}")

        # Evita duplicatas caso a tabela tenha repetições.
        if any(k.value == value for k in items):
            continue
        items.append(Key(name, value))

    for value, name in _EXTRA:
        if any(k.value == value for k in items):
            continue
        items.append(Key(name, value))
    return items


CATALOG = _build_catalog()
BY_VALUE = {k.value: k for k in CATALOG}
BY_NAME = {k.name: k for k in CATALOG}


def key_name(value):
    key = BY_VALUE.get(value)
    if key is not None:
        return key.name
    return f"Desconhecido (0x{value:06X})"


def ensure_value(value):
    """Garante que um valor exista no catálogo (adiciona se desconhecido)."""
    global CATALOG
    if value in BY_VALUE:
        return BY_VALUE[value]
    key = Key(f"Desconhecido (0x{value:06X})", value)
    CATALOG.append(key)
    BY_VALUE[value] = key
    BY_NAME[key.name] = key
    return key
