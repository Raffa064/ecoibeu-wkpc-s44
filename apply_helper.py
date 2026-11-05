#!/usr/bin/python3
"""Aplicador privilegiado do ecoibeu mouse.

Este script é executado como root (via sudo -A + zenity) pela interface.
Ele nunca abre uma janela; apenas conversa com o hidraw e imprime JSON.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wkpc_protocol as protocol  # noqa: E402


def parse_value(text):
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"valor inválido: {text}") from exc
    if not 0 <= value <= 0xFFFFFF:
        raise argparse.ArgumentTypeError("o valor deve caber em 24 bits")
    return value


def main():
    parser = argparse.ArgumentParser(description="Aplica o keymap do mouse")
    parser.add_argument("--forward", type=parse_value,
                        help="atribuição do botão forward (entrada 3)")
    parser.add_argument("--back", type=parse_value,
                        help="atribuição do botão back (entrada 4)")
    parser.add_argument("--probe", action="store_true",
                        help="apenas diagnostica os hidraw, sem gravar nada")
    args = parser.parse_args()

    if args.probe:
        print(json.dumps({"protocol": "probe",
                          "devices": protocol.probe_devices()}))
        return 0

    if args.forward is None or args.back is None:
        parser.error("--forward e --back são obrigatórios (ou use --probe)")

    result = protocol.apply_buttons(args.forward, args.back)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
