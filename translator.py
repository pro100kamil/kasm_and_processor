#!/usr/bin/python3
"""Транслятор Asm в машинный код.
"""

import sys

from isa import Opcode, Term, write_code

SHIFT = 100


def get_meaningful_token(line):
    """Извлекаем из строки содержательный токен (метка или инструкция), удаляем
    комментарии и пробелы в начале/конце строки.
    """
    return line.split(";", 1)[0].strip()


def translate_stage_1(text):
    """Первый проход транслятора. Преобразование текста программы в список
    инструкций и определение адресов меток.

    Особенность: транслятор ожидает, что в строке может быть либо 1 метка,
    либо 1 инструкция. Поэтому: `col` заполняется всегда 0, так как не несёт
    смысловой нагрузки.
    """
    code = []
    labels = {}

    OPCODES_WITH_OPERAND = [Opcode.PRINT_STR,
                            Opcode.JZ, Opcode.JNZ, Opcode.JMP, Opcode.DEC]
    OPCODES_WITH_TWO_OPERANDS = [Opcode.ADD_STR]
    OPCODES_WITH_THREE_OPERANDS = [Opcode.MOV, Opcode.MOD, Opcode.MUL, Opcode.SUB, Opcode.ADD]
    OPCODES_WITH_OPERANDS = OPCODES_WITH_OPERAND + OPCODES_WITH_TWO_OPERANDS + OPCODES_WITH_THREE_OPERANDS

    for line_num, raw_line in enumerate(text.splitlines(), 1):
        token = get_meaningful_token(raw_line)
        if token == "":
            continue

        pc = len(code)

        if token.endswith(":"):  # токен содержит метку
            label = token.strip(":")
            assert label not in labels, "Redefinition of label: {}".format(label)
            labels[label] = SHIFT + pc  # TODO use constant!
        elif " " in token:  # токен содержит инструкцию с операндом (отделены пробелом)
            sub_tokens = token.split(maxsplit=1) if token.startswith(Opcode.ADD_STR.value) else token.split()
            assert len(sub_tokens) == 2, "Invalid instruction: {}".format(token)
            mnemonic, arg = sub_tokens
            arg = arg.split(',')
            opcode = Opcode(mnemonic)
            # assert opcode == Opcode.JZ or opcode == Opcode.JMP, "Only `jz` and `jnz` instructions take an argument"
            assert opcode in OPCODES_WITH_OPERANDS, \
                "This instruction doesn't take an argument"

            code.append({"index": pc, "opcode": opcode, "arg": arg, "term": Term(line_num, 0, token)})
        else:  # токен содержит инструкцию без операндов
            opcode = Opcode(token)
            code.append({"index": pc, "opcode": opcode, "term": Term(line_num, 0, token)})

    return labels, code


def translate_stage_2(labels, code):
    """Второй проход транслятора. В уже определённые инструкции подставляются
    адреса меток."""
    for instruction in code:
        if "arg" in instruction and \
                instruction["opcode"].value in {Opcode.JZ.value,
                                                Opcode.JNZ.value,
                                                Opcode.JMP.value,
                                                Opcode.PRINT_STR.value}:
            label = instruction["arg"]
            assert label[0] in labels, "Label not defined: " + label
            if instruction["opcode"].value in {Opcode.JMP}:
                instruction["arg"] = labels[label[0]]
            elif instruction["opcode"].value == Opcode.PRINT_STR:
                # print(label)
                # print(labels[label[0]])
                # print(code[labels[label[0]] - SHIFT])
                instruction["arg"] = labels[label[0]]
            else:
                instruction["arg"] = labels[label[0]], label[1]
    return code


def translate(text):
    """Трансляция текста программы на Asm в машинный код.

    Выполняется в два прохода:

    1. Разбор текста на метки и инструкции.

    2. Подстановка адресов меток в операнды инструкции.
    """
    labels, code = translate_stage_1(text)
    code = translate_stage_2(labels, code)

    # ruff: noqa: RET504
    return code


def main(source, target):
    """Функция запуска транслятора. Параметры -- исходный и целевой файлы."""
    with open(source, encoding="utf-8") as f:
        source = f.read()

    code = translate(source)

    write_code(target, code)
    print("source LoC:", len(source.split("\n")), "code instr:", len(code))


if __name__ == "__main__":
    assert len(sys.argv) == 3, "Wrong arguments: translator.py <input_file> <target_file>"
    _, source, target = sys.argv
    main(source, target)
