"""Protocolo de 64 bytes do WKPC-S44 / EVISION 3-mode mouse.

Frame:
    [0]     0x04 (report id)
    [1:3]   checksum LE da soma dos bytes [3:64]
    [3]     opcode
    [4]     tamanho do chunk
    [5:7]   offset LE
    [7]     reservado (0)
    [8:64]  payload

Resposta:
    [3]     opcode ecoado
    [7]     status (0xFF = -102, 0xFE = -103, 0x00 = sucesso)
    [8:64]  payload

Sequência de gravação usada pelo app do fabricante:
    BEGIN (0x01) -> SET_KEYMAP (0x09) em chunks -> COMMIT (0x02)

O keymap tem config[5] * 3 bytes (neste mouse: 42 * 3 = 126).
"""

import glob
import os
import select
import time

FRAME_SIZE = 64
REPORT_ID = 0x04
CHUNK_SIZE = 56

OP_BEGIN = 0x01
OP_COMMIT = 0x02
OP_GET_CONFIG = 0x03
OP_GET_KEYMAP = 0x07
OP_SET_KEYMAP = 0x09

CONFIG_SIZE = 34
CONFIG_KEY_COUNT_INDEX = 5

VID = 0x320F
PID = 0x226E
# O mesmo mouse/receiver aparece com PIDs diferentes conforme o modo
# (cabo x dongle 2.4G). Testamos o protocolo em todos os hidraw da EVISION.
KNOWN_PIDS = {0x226E, 0x226F}
ALT_IDS = ((0x0C45, 0x1007),)


class ProtocolError(Exception):
    pass


def checksum(frame):
    return sum(frame[3:FRAME_SIZE]) & 0xFFFF


def build_frame(opcode, chunk_len=0, offset=0, payload=b""):
    frame = bytearray(FRAME_SIZE)
    frame[0] = REPORT_ID
    frame[3] = opcode & 0xFF
    frame[4] = chunk_len & 0xFF
    frame[5] = offset & 0xFF
    frame[6] = (offset >> 8) & 0xFF
    frame[7] = 0
    if payload:
        frame[8:8 + min(len(payload), FRAME_SIZE - 8)] = payload[:FRAME_SIZE - 8]
    cs = checksum(frame)
    frame[1] = cs & 0xFF
    frame[2] = (cs >> 8) & 0xFF
    return bytes(frame)


def _drain(fd):
    while True:
        try:
            ready, _, _ = select.select([fd], [], [], 0)
        except InterruptedError:
            continue
        if not ready:
            return
        try:
            os.read(fd, FRAME_SIZE)
        except OSError:
            return


def exchange(fd, opcode, chunk_len=0, offset=0, payload=b"",
             timeout=2.0, retries=2, need_payload=False):
    """Envia um frame e devolve (status, payload)."""
    last_error = None
    for _ in range(retries + 1):
        _drain(fd)
        frame = build_frame(opcode, chunk_len, offset, payload)
        try:
            written = os.write(fd, frame)
        except OSError as exc:
            raise ProtocolError(f"erro de escrita: {exc}") from exc
        if written != FRAME_SIZE:
            last_error = ProtocolError("escrita incompleta")
            continue

        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            last_error = ProtocolError(
                f"timeout no opcode 0x{opcode:02X} (offset {offset})")
            continue

        try:
            rx = os.read(fd, FRAME_SIZE)
        except OSError as exc:
            last_error = ProtocolError(f"erro de leitura: {exc}")
            continue

        if len(rx) < 8:
            last_error = ProtocolError(f"resposta curta ({len(rx)} bytes)")
            continue
        if rx[3] != opcode:
            last_error = ProtocolError(
                f"opcode retornado 0x{rx[3]:02X} != 0x{opcode:02X}")
            continue

        status = rx[7]
        if status in (0xFF, 0xFE):
            raise ProtocolError(
                f"o dispositivo rejeitou (status 0x{status:02X}, "
                f"opcode 0x{opcode:02X}, offset {offset})")

        if need_payload:
            if len(rx) < 8 + chunk_len:
                last_error = ProtocolError(
                    f"payload curto: pedido {chunk_len}, "
                    f"recebido {max(0, len(rx) - 8)}")
                continue
            return status, bytes(rx[8:8 + chunk_len])

        return status, b""

    raise last_error or ProtocolError("falha de comunicação desconhecida")


def _hid_ids(sys_hidraw_path):
    try:
        with open(os.path.join(sys_hidraw_path, "device", "uevent"),
                  "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("HID_ID="):
                    parts = line.strip().split("=", 1)[1].split(":")
                    if len(parts) == 3:
                        return int(parts[1], 16), int(parts[2], 16)
    except OSError:
        return None
    return None


def _hidraw_sort_key(path):
    suffix = os.path.basename(path)[len("hidraw"):]
    return int(suffix) if suffix.isdigit() else 9999


def _ids_match(ids):
    if ids is None:
        return False
    vendor, product = ids
    return ((vendor == VID and product in KNOWN_PIDS) or
            (vendor, product) in ALT_IDS)


def _iter_candidate_devices():
    for dev_path in sorted(glob.glob("/dev/hidraw*"), key=_hidraw_sort_key):
        sys_path = os.path.join("/sys/class/hidraw", os.path.basename(dev_path))
        ids = _hid_ids(sys_path)
        if _ids_match(ids):
            yield dev_path, ids


def find_device():
    """Abre o hidraw que responde ao protocolo. Devolve (fd, caminho)."""
    for dev_path, _ids in _iter_candidate_devices():
        try:
            fd = os.open(dev_path, os.O_RDWR)
        except OSError:
            continue

        try:
            exchange(fd, OP_GET_CONFIG, CONFIG_SIZE, 0,
                     timeout=1.5, retries=3, need_payload=True)
            return fd, dev_path
        except ProtocolError:
            os.close(fd)

    raise ProtocolError(
        "mouse não encontrado (EVISION 320F:226E/226F) ou sem permissão em "
        "/dev/hidraw*. Rode o aplicativo e autorize no zenity.")


def probe_devices():
    """Diagnóstico read-only de todos os hidraw candidatos."""
    results = []
    for dev_path, ids in _iter_candidate_devices():
        item = {
            "device": dev_path,
            "vendor": f"0x{ids[0]:04X}",
            "product": f"0x{ids[1]:04X}",
            "config_status": None,
            "key_count": None,
            "keymap_chunk_56": None,
            "keymap_chunk_24": None,
            "error": None,
        }
        try:
            fd = os.open(dev_path, os.O_RDWR)
        except OSError as exc:
            item["error"] = f"open: {exc}"
            results.append(item)
            continue

        try:
            config = read_block(fd, OP_GET_CONFIG, CONFIG_SIZE, chunk_size=56)
            item["config_status"] = 0
            item["key_count"] = config[CONFIG_KEY_COUNT_INDEX]
            for size in (56, 24):
                try:
                    _status, payload = exchange(
                        fd, OP_GET_KEYMAP, size, 0, timeout=1.5, retries=1,
                        need_payload=True)
                    item[f"keymap_chunk_{size}"] = f"ok ({len(payload)} bytes)"
                except ProtocolError as exc:
                    item[f"keymap_chunk_{size}"] = f"falhou: {exc}"
        except ProtocolError as exc:
            item["error"] = str(exc)
        finally:
            os.close(fd)
        results.append(item)
    return results


def read_block(fd, opcode, total, chunk_size=CHUNK_SIZE):
    out = bytearray()
    while len(out) < total:
        chunk = min(chunk_size, total - len(out))
        _, payload = exchange(fd, opcode, chunk, len(out),
                              timeout=2.0, retries=3, need_payload=True)
        if len(payload) != chunk:
            raise ProtocolError(
                f"chunk curto no opcode 0x{opcode:02X}: "
                f"esperado {chunk}, recebido {len(payload)}")
        out.extend(payload)
    return bytes(out)


def read_config(fd):
    return read_block(fd, OP_GET_CONFIG, CONFIG_SIZE)


def read_keymap(fd, key_count, chunk_size=CHUNK_SIZE):
    return read_block(fd, OP_GET_KEYMAP, key_count * 3, chunk_size=chunk_size)


def entry_value(keymap, index):
    offset = index * 3
    return int.from_bytes(keymap[offset:offset + 3], "big")


def set_entry(keymap, index, value):
    if not 0 <= value <= 0xFFFFFF:
        raise ProtocolError(f"valor fora do intervalo: 0x{value:X}")
    offset = index * 3
    keymap[offset:offset + 3] = value.to_bytes(3, "big")


def write_keymap(fd, keymap):
    """BEGIN -> SET_KEYMAP em chunks -> COMMIT. Devolve os status recebidos."""
    statuses = []

    status, _ = exchange(fd, OP_BEGIN, 0, 0, timeout=1.5, retries=2)
    statuses.append({"op": "BEGIN", "offset": 0, "status": status})
    time.sleep(0.01)

    done = 0
    while done < len(keymap):
        chunk = min(CHUNK_SIZE, len(keymap) - done)
        status, _ = exchange(fd, OP_SET_KEYMAP, chunk, done,
                             keymap[done:done + chunk], timeout=2.0, retries=2)
        statuses.append({"op": "SET_KEYMAP", "offset": done, "status": status})
        done += chunk
        time.sleep(0.002)

    time.sleep(0.01)
    try:
        status, _ = exchange(fd, OP_COMMIT, 0, 0, timeout=1.0, retries=0)
        statuses.append({"op": "COMMIT", "offset": 0, "status": status})
    except ProtocolError:
        # Algumas revisões de firmware não respondem ao COMMIT.
        statuses.append({"op": "COMMIT", "offset": 0, "status": None})

    return statuses


def apply_buttons(forward_value, back_value):
    """Lê o keymap atual, troca as entradas 3 (forward) e 4 (back) e grava.

    Devolve um dicionário com o resultado. Não levanta exceção para falhas
    de protocolo; o erro é colocado em ``error``.
    """
    fd = None
    result = {
        "ok": False,
        "device": None,
        "key_count": None,
        "keymap_len": None,
        "forward": forward_value,
        "back": back_value,
        "before_forward": None,
        "before_back": None,
        "after_forward": None,
        "after_back": None,
        "readback_matches": None,
        "statuses": [],
        "keymap_before_hex": None,
        "error": None,
    }

    try:
        fd, dev_path = find_device()
        result["device"] = dev_path

        config = read_config(fd)
        key_count = config[CONFIG_KEY_COUNT_INDEX]
        if key_count <= 0:
            raise ProtocolError(f"config[5] inválido: {key_count}")
        result["key_count"] = key_count
        result["keymap_len"] = key_count * 3

        original = read_keymap(fd, key_count)
        result["keymap_before_hex"] = original.hex()
        result["before_forward"] = entry_value(original, 3)
        result["before_back"] = entry_value(original, 4)

        desired = bytearray(original)
        set_entry(desired, 3, forward_value)
        set_entry(desired, 4, back_value)

        result["statuses"] = write_keymap(fd, desired)

        time.sleep(0.1)
        _drain(fd)
        readback = read_keymap(fd, key_count)
        result["after_forward"] = entry_value(readback, 3)
        result["after_back"] = entry_value(readback, 4)
        result["readback_matches"] = (
            result["after_forward"] == forward_value and
            result["after_back"] == back_value
        )
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - queremos devolver o erro em JSON
        result["error"] = str(exc)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    return result
