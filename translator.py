"""Транслятор Asm в машинный код."""

import sys

from isa import Opcode, Term, write_code

SHIFT = 100


def get_meaningful_token(line: str) -> str:
    """Извлекаем из строки содержательный токен (метка или инструкция), удаляем
    комментарии и пробелы в начале/конце строки.
    """
    return line.split(";", 1)[0].strip()


def translate_stage_1(text: str) -> tuple[dict, dict, list, list]:
    """Первый проход транслятора. Преобразование текста программы в список
    инструкций и определение адресов меток.

    Особенность: транслятор ожидает, что в строке может быть либо 1 метка,
    либо 1 инструкция. Поэтому: `col` заполняется всегда 0, так как не несёт
    смысловой нагрузки.
    """
    code = []
    label2command_address = {}
    label2str_address = {}
    data = []

    OPCODES_WITH_OPERAND = [Opcode.PRINT_STR,
                            Opcode.JMP,
                            Opcode.DEC, Opcode.INC]
    OPCODES_WITH_TWO_OPERANDS = [Opcode.JZ, Opcode.JNZ, Opcode.ADD_STR, Opcode.STORE]
    OPCODES_WITH_THREE_OPERANDS = [Opcode.MOV, Opcode.MOD, Opcode.MUL, Opcode.SUB, Opcode.ADD]
    OPCODES_WITH_OPERANDS = OPCODES_WITH_OPERAND + OPCODES_WITH_TWO_OPERANDS + OPCODES_WITH_THREE_OPERANDS

    last_label = None

    for line_num, raw_line in enumerate(text.splitlines(), 1):
        token = get_meaningful_token(raw_line)
        if token == "":
            continue

        pc = len(code)

        if token.endswith(":"):  # токен содержит метку
            label = token.strip(":")
            assert label not in label2command_address, "Redefinition of label: {}".format(label)
            label2command_address[label] = SHIFT + pc

            last_label = label
        elif " " in token:  # токен содержит инструкцию с операндом (отделены пробелом)
            sub_tokens = token.split(maxsplit=1) if token.startswith(Opcode.ADD_STR.value) else token.split()
            assert len(sub_tokens) == 2, "Invalid instruction: {}".format(token)
            mnemonic, arg = sub_tokens
            arg = arg.split(',')
            opcode = Opcode(mnemonic)

            assert opcode in OPCODES_WITH_OPERANDS, \
                f"This instruction ({opcode}) doesn't take an argument"

            code.append({"index": pc, "opcode": opcode, "arg": arg, "term": Term(line_num, 0, token)})

            if opcode.value == Opcode.ADD_STR:
                if last_label is not None:
                    label2str_address[last_label] = len(data)

                data.append(int(arg[0]))
                for let in arg[1][1:-1]:
                    data.append(ord(let))

            last_label = None
        else:  # токен содержит инструкцию без операндов
            opcode = Opcode(token)
            code.append({"index": pc, "opcode": opcode, "term": Term(line_num, 0, token)})

            last_label = None

    return label2command_address, label2str_address, code, data


def translate_stage_2(label2command_address: dict, label2str_address: dict, code: list):
    """Второй проход транслятора. В уже определённые инструкции подставляются
    адреса меток."""
    for instruction in code:
        if "arg" in instruction and \
                instruction["opcode"].value in {Opcode.JZ.value,
                                                Opcode.JNZ.value,
                                                Opcode.JMP.value,
                                                Opcode.PRINT_STR.value}:
            label = instruction["arg"]
            if label[0].isdigit():
                continue
            assert label[0] in label2command_address, "Label not defined: " + label[0]
            if instruction["opcode"].value in {Opcode.JMP}:
                instruction["arg"] = label2command_address[label[0]]
            elif instruction["opcode"].value == Opcode.PRINT_STR:
                instruction["arg"] = [label2str_address[label[0]]]
            else:
                instruction["arg"] = label2command_address[label[0]], label[1]
    return code


def translate(text: str) -> list:
    """Трансляция текста программы на Asm в машинный код.

    Выполняется в два прохода:

    1. Разбор текста на метки и инструкции.

    2. Подстановка адресов меток в операнды инструкции.
    """
    label2command_address, label2str_address, code, data = translate_stage_1(text)
    code = translate_stage_2(label2command_address, label2str_address, code)
    empty_data_count = SHIFT - len(data)
    memory = data + empty_data_count * [0] + code

    return memory


def main(source: str, target: str) -> None:
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
