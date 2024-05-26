import json
from collections import namedtuple
from enum import Enum


class Opcode(str, Enum):
    """Opcode для инструкций."""

    INC = "inc"
    DEC = "dec"
    INPUT = "input"
    PRINT = "print"

    JMP = "jmp"
    JZ = "jz"
    JNZ = "jnz"

    HALT = "halt"

    MOV = "mov"

    ADD = "add"
    SUB = "sub"
    MOD = "mod"
    MUL = "mul"

    ADD_STR = "add_str"
    PRINT_STR = "print_str"

    EI = "ei"
    DI = "di"
    IRET = "iret"

    STORE = "store"

    RIGHT = "right"
    LEFT = "left"

    LD = "ld"  # don't use

    PRINT_CHAR = "print_char"

    CALL = "call"
    RET = "ret"

    def __str__(self):
        """Переопределение стандартного поведения `__str__` для `Enum`: вместо
        `Opcode.INC` вернуть `increment`.
        """
        return str(self.value)


class Term(namedtuple("Term", "line pos symbol")):
    """Описание выражения из исходного текста программы.

    Сделано через класс, чтобы был docstring.
    """


def write_code(filename, code):
    """Записать машинный код в файл."""
    with open(filename, "w", encoding="utf-8") as file:
        buf = []
        for instr in code:
            buf.append(json.dumps(instr))
        file.write("[" + ",\n ".join(buf) + "]")


def read_code(filename: str) -> list:
    """Прочесть машинный код из файла.

    Так как в файле хранятся не только простейшие типы (`Opcode`, `Term`), мы
    также выполняем конвертацию в объекты классов вручную (возможно, следует
    переписать через `JSONDecoder`, но это скорее усложнит код).

    """
    with open(filename, encoding="utf-8") as file:
        code = json.loads(file.read())

    for instr in code:
        # Конвертация строки в Opcode
        if isinstance(instr, dict):
            instr["opcode"] = Opcode(instr["opcode"])

            # Конвертация списка term в класс Term
            if "term" in instr:
                assert len(instr["term"]) == 3
                instr["term"] = Term(instr["term"][0], instr["term"][1], instr["term"][2])

    return code
