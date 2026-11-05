# ecoibeu mouse

Vibecoded app to remap the side buttons of the **WKPC-S44 / EVISION 3-mode**
mouse directly on the device, using a proprietary protocol reverse-engineered
from the vendor's own software.

The mouse exposes the same interface as `320f:226e` over USB and `320f:226f`
over the 2.4 GHz receiver. The app probes every matching `hidraw` node and
talks to whichever one answers the protocol.

## Requirements

- Linux with GTK3 and PyGObject for the system Python (`/usr/bin/python3`).
- Read/write access to the mouse's `/dev/hidraw*` node, granted through `sudo`.

## Running

From a release, use the AppImage:

```sh
./ecoibeu-mouse-x86_64.AppImage
```

From source:

```sh
./run.sh
# or
/usr/bin/python3 app.py
```

The AppImage does not bundle Python or GTK: it uses the system interpreter.
Make sure `/usr/bin/python3` has `gi` (PyGObject) and GTK3 available.

To add it to the application menu:

```sh
make install     # installs to ~/.local, remove with: make uninstall
```

## Usage

1. Create a profile and choose what the **forward** and **back** side buttons
   should do. The key fields are searchable, so typing part of a key name
   filters the catalog.
2. Apply the profile to the mouse.

Profiles are stored on the computer, not on the mouse. Only one profile can be
marked as default; it is applied with a single action. Applying writes the
current keymap to the device: forward is keymap entry 3 and back is entry 4.

Configuration changes need root to open the hidraw device. The app keeps its
own UI unprivileged and runs `apply_helper.py` through `sudo -A`, using a
temporary askpass script backed by `zenity` to request the password. Before
escalating, the helper and protocol module are copied to
`~/.cache/ecoibeu-mouse/helper/`, because the root process cannot read files
inside a user-mounted AppImage.

A backup of the previous keymap is saved on every write.

### Command line

The helper can also be used directly as root:

```sh
# read-only diagnostics: list candidate devices and protocol responses
sudo /usr/bin/python3 apply_helper.py --probe

# set forward and back (values are 24-bit key assignments)
sudo /usr/bin/python3 apply_helper.py --forward 0x100800 --back 0x100400
```

It prints a JSON object describing the device, key count, previous and new
entries, write statuses, and any error. Exit status is `0` on success.

## Protocol

### Transport

The device is driven over raw HID reports on `/dev/hidrawN`. Every message is
exactly **64 bytes**:

| Bytes | Field |
|---|---|
| `0` | Report ID: `0x04` |
| `1:3` | Checksum, little-endian |
| `3` | Opcode |
| `4` | Chunk length |
| `5:7` | Offset, little-endian |
| `7` | Reserved (`0`) in requests; status in responses |
| `8:64` | Payload (up to 56 bytes) |

The checksum is the 16-bit sum of bytes `3` through `63` (`sum(frame[3:64]) &
0xFFFF`), stored little-endian in bytes 1 and 2.

A response echoes the opcode in byte 3, puts a status in byte 7, and returns
the payload from byte 8. Status `0x00` means success; `0xFF` and `0xFE` are
rejections (`-102` and `-103`). Requests are retried on timeout or short
reads.

### Operations

| Opcode | Name | Purpose |
|---|---|---|
| `0x01` | `BEGIN` | Start a keymap write transaction |
| `0x02` | `COMMIT` | Commit the written keymap |
| `0x03` | `GET_CONFIG` | Read the 34-byte configuration block |
| `0x07` | `GET_KEYMAP` | Read keymap bytes at an offset |
| `0x09` | `SET_KEYMAP` | Write keymap bytes at an offset |

Reads and writes are chunked, with a maximum of 56 payload bytes per frame and
an offset that advances by the chunk length each time.

### Device discovery

The app looks for `/dev/hidraw*` whose HID IDs match vendor `0x320F` with
product `0x226E` or `0x226F`, or the alternate pair `0x0C45:0x1007`. Each
candidate is opened and probed with `GET_CONFIG`; the first device that
answers is used.

### Configuration and keymap

`GET_CONFIG` returns 34 bytes. Byte 5 is the number of keymap entries:

```
keymap_size = config[5] * 3
```

On this mouse `config[5]` is `42`, so the keymap is **126 bytes**. Each entry
is **3 bytes, big-endian**, holding a 24-bit key assignment:

| Entry | Button |
|---|---|
| `3` | Forward |
| `4` | Back |

Key assignment values:

- Keyboard keys use `0x20 MM UU`, where `MM` is the HID modifier mask and
  `UU` is the HID keyboard usage. Examples: left Shift `0x200200`, left Alt
  `0x200400`, `A` `0x200004`.
- Mouse buttons: left `0x100100`, right `0x100200`, middle `0x100400`,
  back `0x100800`, forward `0x101000`.
- Disabled: `0xA00000`.

The key catalog contains 91 keyboard entries extracted from the vendor
executable (`WKPC-S44 MOUSE.exe`, file offset `0x2d2e38`), plus the mouse
buttons and the disabled value. Unknown 24-bit values are still accepted and
shown as raw values.

### Writing a keymap

The vendor write sequence is:

```
BEGIN (0x01)
  SET_KEYMAP (0x09), chunks of 56 bytes at increasing offsets
COMMIT (0x02)
```

The app reads the current keymap, replaces only entries 3 and 4, and writes
the full keymap back using that sequence. After writing it reads the keymap
again for verification.

Two firmware quirks are handled:

- Some revisions do not answer `COMMIT`. This is not treated as a failure.
- `GET_KEYMAP` may keep returning the old values after an accepted write.
  Success is determined by the ACKs (`status 0x00`), not by readback.

## Files and data

| Path | Contents |
|---|---|
| `~/.config/ecoibeu-mouse/profiles.json` | Profiles and default profile |
| `~/.local/share/ecoibeu-mouse/backups/` | Keymap backups |
| `~/.cache/ecoibeu-mouse/askpass.sh` | Temporary sudo askpass script |
| `~/.cache/ecoibeu-mouse/helper/` | Helper copy executed by root |

| File | Purpose |
|---|---|
| `app.py` | GTK3 interface |
| `wkpc_protocol.py` | Frame encoding, device discovery, keymap read/write |
| `apply_helper.py` | Privileged entry point; prints JSON |
| `key_catalog.py` | Key table extracted from the vendor executable |
| `run.sh` | Runs the app with the system Python |
| `Makefile` | AppImage build and installation |
