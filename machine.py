from __future__ import annotations

import logging
import sys
from typing import ClassVar

from exceptions import UnknownCommandError
from isa import Opcode, read_code

INTERRUPTION_VECTOR_INDEX = 99


class Memory:
    """Память фон Неймановская архитектура"""

    def __init__(self, data_memory_size: int, code: list):
        self.shift = data_memory_size
        self.memory = code.copy()


class ALU:
    """Арифметико-логическое устройство"""

    operations: ClassVar[dict] = {
        Opcode.INC: lambda left, right: left + 1,
        Opcode.DEC: lambda left, right: left - 1,
        Opcode.MOV: lambda left, right: left,
        Opcode.ADD: lambda left, right: left + right,
        Opcode.SUB: lambda left, right: left - right,
        Opcode.MOD: lambda left, right: left % right,
        Opcode.MUL: lambda left, right: left * right,
    }
    zero = None
    res = None

    def calc(self, op: Opcode, left: int, right: int) -> int:
        self.res = self.operations.get(op)(left, right)
        self.zero = self.res == 0
        return self.res


class InterruptionController:
    """Контроллер прерываний"""

    interruption: bool = None
    interruption_number: int = None

    def __init__(self):
        self.interruption = False
        self.interruption_number = 0

    def generate_interruption(self, number: int) -> None:
        assert number == 1, f"Unknown interruption number: {number}"
        self.interruption = True
        self.interruption_number = number


class DataPath:
    """Тракт данных, включая: ввод/вывод, память и арифметику."""

    memory: Memory = None

    alu: ALU = None

    data_address: int = None

    new_data_address: int = None

    buffer: int = None

    data_register: int = None
    input_register: int = None

    program_counter: int = None
    "Счётчик команд. Инициализируется сдвигом, потому что данные лежат до команд."

    prev_program_counter: int = None

    output_buffer: list = None

    registers: ClassVar[dict[str, int]] = {
        "acc": 0,
        "r1": 0,
        "r2": 0,
        "r3": 0,
        "r4": 0,
        "rc": 0,  # "r5": 0,
        "rs": 0,  # "r6": 0,
        "r7": 0,
    }

    imml: int = None
    immr: int = None

    alu_l_value: int = None
    alu_r_value: int = None

    interruption_controller: InterruptionController = None

    def __init__(self, alu: ALU, memory: Memory):
        self.memory = memory
        self.alu = alu
        self.data_address = memory.memory.index(0)
        self.new_data_address = memory.memory.index(0)

        self.buffer = 0

        self.program_counter = memory.shift
        self.data_register = 0
        self.input_register = 0

        self.output_buffer = []

        self.interruption_controller = InterruptionController()

    def signal_latch_program_counter(self, sel_next):
        """Защёлкнуть новое значение счётчика команд.

        Если `sel_next` равен `True`, то счётчик будет увеличен на единицу,
        иначе -- будет установлен в значение аргумента текущей инструкции.
        """
        if sel_next:
            self.program_counter += 1
        else:
            self.program_counter = self.data_register

    def signal_latch_input_register(self, value):
        """Защёлкнуть новое значение регистра ввода."""
        self.input_register = value

    def signal_latch_data_register(self, value):
        """Защёлкнуть новое значение регистра ввода."""
        self.data_register = value

    def signal_latch_data_addr(self, sel):
        """Защёлкнуть адрес в памяти данных. Защёлкивание осуществляется на
        основе селектора `sel` в котором указывается `Opcode`:

        - `Opcode.LEFT.value` -- сдвиг влево;

        - `Opcode.RIGHT.value` -- сдвиг вправо.

        При выходе за границы памяти данных процесс моделирования останавливается.
        """
        assert sel in {Opcode.LEFT.value, Opcode.RIGHT.value}, "internal error, incorrect selector: {}".format(sel)

        if sel == Opcode.LEFT.value:
            self.data_address -= 1
            self.new_data_address -= 1
        elif sel == Opcode.RIGHT.value:
            self.data_address += 1
            self.new_data_address += 1

        assert 0 <= self.data_address < len(self.memory.memory), "out of memory: {}".format(self.data_address)

    def signal_latch_acc(self):
        """Защёлкнуть слово из памяти (`oe` от Output Enable) и защёлкнуть его в
        аккумулятор. Сигнал `oe` выставляется неявно `ControlUnit`-ом.
        """
        self.registers["acc"] = self.memory.memory[self.data_address]

    def signal_latch_r(self, register_name: str, value):
        # для r1, ..., r7 (регистров общего назначения)
        self.registers[register_name] = value

    def signal_alu_l(self, sel: str):
        if sel == "imml":
            self.alu_l_value = self.imml
        else:
            self.alu_l_value = self.registers.get(sel)

    def signal_alu_r(self, sel: str):
        if sel == "0":
            self.alu_r_value = 0
        elif sel == "immr":
            self.alu_r_value = self.immr
        else:
            self.alu_r_value = self.registers.get(sel)

    def signal_alu_op(self, sel: Opcode):
        res = self.alu.calc(sel, self.alu_l_value, self.alu_r_value)
        assert res is not None, "unknown instruction"
        return res

    def signal_wr(self, sel):
        """wr (от WRite), сохранить в память.

        Запись в память осуществляется на основе селектора `sel` в котором указывается `Opcode`:

        - `Opcode.INC.value` -- инкремент аккумулятора;

        - `Opcode.DEC.value` -- декремент аккумулятора;

        - `Opcode.INPUT.value` -- ввод из буфера входных данных. При исчерпании
          буфера -- выбрасывается исключение `EOFError`.

        В примере ниже имитируется переполнение ячейки при инкременте. Данный
        текст является doctest-ом, корректность которого проверяется во время
        загрузки модуля или командой: `python3 -m doctest -v machine.py`
        """
        assert sel in {
            Opcode.INC.value,
            Opcode.DEC.value,
            Opcode.INPUT.value,
        }, "internal error, incorrect selector: {}".format(sel)

        if sel == Opcode.INC.value:
            self.memory.memory[self.data_address] = self.registers["acc"] + 1
            if self.memory.memory[self.data_address] == 128:
                self.memory.memory[self.data_address] = -128
        elif sel == Opcode.DEC.value:
            self.memory.memory[self.data_address] = self.registers["acc"] - 1
            if self.memory.memory[self.data_address] == -129:
                self.memory.memory[self.data_address] = 127
        elif sel == Opcode.INPUT.value:
            self.data_address = self.new_data_address

            symbol_code = self.input_register
            symbol = chr(symbol_code)
            assert -128 <= symbol_code <= 127, "input token is out of bound: {}".format(symbol_code)
            self.memory.memory[self.data_address] = symbol_code
            self.registers["acc"] = symbol_code
            logging.debug("input: %s", repr(symbol))

    def signal_output(self):
        """Вывести значение аккумулятора в порт вывода.

        Вывод осуществляется путём конвертации значения аккумулятора в символ по
        ASCII-таблице.
        """
        symbol = chr(self.registers["acc"])
        logging.debug("output: %s << %s", repr("".join(self.output_buffer)), repr(symbol))
        self.output_buffer.append(symbol)

    def zero(self):
        """Флаг нуля. Необходим для условных переходов."""
        return self.alu.zero


class ControlUnit:
    """Блок управления процессора. Выполняет декодирование инструкций и
    управляет состоянием модели процессора, включая обработку данных (DataPath).
    """

    data_path: DataPath = None
    "Блок обработки данных."

    _tick: int = None
    "Текущее модельное время процессора (в тактах). Инициализируется нулём."

    handling_interruption: bool = None
    "Происходит ли в данный момент обработка прерывания"

    interruption_enabled: bool = None
    "Разрешены ли прерывания"

    def __init__(self, memory: Memory, data_path: DataPath):
        self.memory = memory

        self.data_path = data_path
        self._tick = 0

        self.handling_interruption = False
        self.interruption_enabled = False

    def tick(self):
        """Продвинуть модельное время процессора вперёд на один такт."""
        self._tick += 1

    def current_tick(self):
        """Текущее модельное время процессора (в тактах)."""
        return self._tick

    def check_and_handle_interruption(self) -> None:
        if not self.interruption_enabled:
            return
        if not self.data_path.interruption_controller.interruption:
            return
        # во время прерывания не может быть другое прерывание
        if self.handling_interruption:
            return

        self.handling_interruption = True

        self.data_path.program_counter = self.memory.memory[INTERRUPTION_VECTOR_INDEX]

        logging.debug("START HANDLING INTERRUPTION")
        return

    def decode_and_execute_control_flow_instruction(self, instr, opcode, phase):
        """Декодировать и выполнить инструкцию управления потоком исполнения. В
        случае успеха -- вернуть `True`, чтобы перейти к следующей инструкции.
        """
        if opcode is Opcode.HALT:
            raise StopIteration()

        if opcode is Opcode.CALL:
            addr = instr["arg"]

            self.data_path.prev_program_counter = self.data_path.program_counter

            self.data_path.signal_latch_data_register(addr)

            self.data_path.signal_latch_program_counter(sel_next=False)
            self.tick()

            return True

        if opcode is Opcode.RET:
            addr = self.data_path.prev_program_counter + 1

            self.data_path.signal_latch_data_register(addr)

            self.data_path.prev_program_counter = None

            self.data_path.signal_latch_program_counter(sel_next=False)
            self.tick()

            return True

        if opcode is Opcode.JMP:
            addr = instr["arg"]

            self.data_path.signal_latch_data_register(addr)

            self.data_path.signal_latch_program_counter(sel_next=False)
            self.tick()

            return True

        if opcode is Opcode.JZ:
            return self.execute_jz(instr, phase)

        if opcode is Opcode.JNZ:
            return self.execute_jnz(instr, phase)

        return False  # чтобы понимать, что текущая инструкция не управляет потоком выполнения

    def execute_jz(self, instr, phase):
        addr, reg = instr["arg"]
        # в 2 такта
        if phase == 1:
            self.data_path.signal_alu_l(reg)
            self.data_path.signal_alu_r("0")

            # выполняется сложение с нулём, чтобы потом проверить результат на zero_flag
            self.data_path.signal_alu_op(Opcode.ADD)

            self.tick()
            return None

        if self.data_path.zero():
            self.data_path.signal_latch_data_register(addr)
            self.data_path.signal_latch_program_counter(sel_next=False)
        else:
            self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()

        return True

    def execute_jnz(self, instr, phase):
        addr, reg = instr["arg"]
        # в 2 такта
        if phase == 1:
            self.data_path.signal_alu_l(reg)
            self.data_path.signal_alu_r("0")

            # выполняется сложение с нулём, чтобы потом проверить результат на zero_flag
            self.data_path.signal_alu_op(Opcode.ADD)

            self.tick()
            return None

        if not self.data_path.zero():
            self.data_path.signal_latch_data_register(addr)
            self.data_path.signal_latch_program_counter(sel_next=False)
        else:
            self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()

        return True

    def execute_print(self, instr, opcode, phase):
        if phase == 1:
            self.data_path.signal_latch_acc()
            self.tick()
            return None

        self.data_path.signal_output()
        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_print_char(self, instr, opcode, phase):
        arg = instr["arg"][0]
        if isinstance(arg, str) and arg[0] == "r" and arg[1:].isdigit():
            self.data_path.data_address = self.data_path.registers.get(arg)
        else:
            self.data_path.data_address = instr["arg"][0]

        self.data_path.signal_latch_acc()
        self.data_path.signal_output()

        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_binary_operation(self, instr, opcode, phase):
        args: list[str]
        args = instr["arg"]
        a, b, c = args
        assert a in self.data_path.registers, "unknown register"

        if b.isdigit():
            self.data_path.imml = int(b)
            self.data_path.signal_alu_l("imml")
        else:
            self.data_path.signal_alu_l(b)

        if c.isdigit():
            self.data_path.immr = int(c)
            self.data_path.signal_alu_r("immr")
        else:
            self.data_path.signal_alu_r(c)

        self.data_path.signal_alu_op(instr["opcode"])

        value = self.data_path.alu.res
        self.data_path.signal_latch_r(a, value)

        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_unary_operation(self, instr, opcode, phase):
        args = instr["arg"]
        a = args[0]
        assert a in self.data_path.registers, "unknown register"

        self.data_path.signal_alu_l(a)
        self.data_path.signal_alu_r("0")

        self.data_path.signal_alu_op(instr["opcode"])

        value = self.data_path.alu.res
        self.data_path.signal_latch_r(a, value)

        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_mov(self, instr, opcode, phase):
        args = instr["arg"]
        a, b = args
        assert a in self.data_path.registers, "unknown register"

        if b.isdigit():
            self.data_path.imml = int(b)
            self.data_path.signal_alu_l("imml")
        elif b == "addr":
            self.data_path.imml = self.data_path.new_data_address
            self.data_path.signal_alu_l("imml")
        else:  # register
            self.data_path.signal_alu_l(b)

        self.data_path.signal_alu_r("0")  # сложение с нулём

        self.data_path.signal_alu_op(Opcode.ADD)

        self.data_path.signal_latch_r(a, self.data_path.alu.res)

        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_store(self, instr, opcode, phase):
        args: list[str]
        args = instr["arg"]
        a, b = args
        b: str
        if a.isdigit():
            a = int(a)
        else:
            a = self.data_path.registers.get(a)
        if b.isdigit():
            self.memory.memory[a] = int(b)
        else:
            self.memory.memory[a] = self.data_path.registers.get(b)

        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_ei(self, instr, opcode, phase):
        self.interruption_enabled = True
        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()
        return True

    def execute_di(self, instr, opcode, phase):
        self.interruption_enabled = False
        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()

        return True

    def execute_iret(self, instr, opcode, phase):
        self.handling_interruption = False
        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()

        self.data_path.interruption_controller.interruption = False

        logging.debug("STOP HANDLING INTERRUPTION")

        return True

    def execute_input(self, instr, opcode, phase):
        self.data_path.signal_wr(opcode.value)
        self.data_path.signal_latch_program_counter(sel_next=True)
        self.tick()

        return True

    def decode_and_execute_instruction(self, phase):
        """Основной цикл процессора. Декодирует и выполняет инструкцию.

        Обработка инструкции:

        1. Проверить `Opcode`.

        2. Вызвать методы, имитирующие необходимые управляющие сигналы.

        3. Продвинуть модельное время вперёд на один такт (`tick`).

        4. (если необходимо) повторить шаги 2-3.

        5. Перейти к следующей инструкции.

        Обработка функций управления потоком исполнения вынесена в
        `decode_and_execute_control_flow_instruction`.
        """
        instr = self.memory.memory[self.data_path.program_counter]

        opcode = instr["opcode"]

        res = self.decode_and_execute_control_flow_instruction(instr, opcode, phase)
        if res is None or res:
            # None - если мы не закончили выполенение инструкции
            # True - если мы полностью выполнили инструкцию
            return res

        if opcode in {Opcode.RIGHT, Opcode.LEFT}:
            self.data_path.signal_latch_data_addr(opcode.value)
            self.data_path.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        if opcode == Opcode.ADD_STR:
            # TODO убрать
            self.data_path.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        if opcode in {Opcode.MOD, Opcode.MUL, Opcode.ADD, Opcode.SUB}:
            return self.execute_binary_operation(instr, opcode, phase)

        if opcode in {Opcode.DEC, Opcode.INC}:
            return self.execute_unary_operation(instr, opcode, phase)

        opcode2handler = {
            Opcode.MOV: self.execute_mov,
            Opcode.PRINT_CHAR: self.execute_print_char,
            Opcode.STORE: self.execute_store,
            Opcode.EI: self.execute_ei,
            Opcode.DI: self.execute_di,
            Opcode.IRET: self.execute_iret,
            Opcode.PRINT: self.execute_print,
            Opcode.INPUT: self.execute_input
        }

        if opcode not in opcode2handler:
            print(opcode)
            raise UnknownCommandError(opcode.value)

        func = opcode2handler[opcode]

        return func(instr, opcode, phase)

    def __repr__(self):
        """Вернуть строковое представление состояния процессора."""
        state_repr = "TICK: {:3} PC: {:3} ADDR: {:3} MEM_OUT: {} ACC: {} rs: {} rc: {} r1: {} r2: {} r3: {}".format(
            self._tick,
            self.data_path.program_counter,
            self.data_path.data_address,
            self.memory.memory[self.data_path.data_address],
            self.data_path.registers.get("acc"),
            self.data_path.registers.get("rs"),
            self.data_path.registers.get("rc"),
            self.data_path.registers.get("r1"),
            self.data_path.registers.get("r2"),
            self.data_path.registers.get("r3"),
        )
        instr = self.memory.memory[self.data_path.program_counter]
        opcode = instr["opcode"]
        instr_repr = str(opcode)

        if "arg" in instr:
            instr_repr += " {}".format(instr["arg"])

        if "term" in instr:
            term = instr["term"]
            instr_repr += "  ('{}'@{}:{})".format(term.symbol, term.line, term.pos)

        return "{} \t{}".format(state_repr, instr_repr)


def initiate_interruption(control_unit: ControlUnit, input_tokens: list):
    if (
            not control_unit.handling_interruption
            and control_unit.interruption_enabled
            and len(input_tokens) != 0
            and not control_unit.data_path.interruption_controller.interruption
    ):
        next_token = input_tokens[0]
        if control_unit.current_tick() > next_token[0]:
            control_unit.data_path.interruption_controller.generate_interruption(1)
            if next_token[1]:
                control_unit.data_path.signal_latch_input_register(ord(next_token[1]))
            else:
                control_unit.data_path.signal_latch_input_register(0)

            return input_tokens[1:]
    return input_tokens


def simulation(code: list, input_tokens: list, data_memory_size: int, limit: int):
    """Подготовка модели и запуск симуляции процессора.

    Длительность моделирования ограничена:

    - количеством выполненных инструкций (`limit`);

    - количеством данных ввода (`input_tokens`, если ввод используется), через
      исключение `EOFError`;

    - инструкцией `Halt`, через исключение `StopIteration`.
    """
    memory = Memory(data_memory_size, code)
    alu = ALU()

    data_path = DataPath(alu, memory)
    control_unit = ControlUnit(memory, data_path)
    instr_counter = 0

    logging.debug("%s", control_unit)
    try:
        while instr_counter < limit:
            phase = 1

            input_tokens = initiate_interruption(control_unit, input_tokens)
            control_unit.check_and_handle_interruption()

            while control_unit.decode_and_execute_instruction(phase) is None:
                phase += 1
                logging.debug("%s", control_unit)
            logging.debug("%s", control_unit)
            instr_counter += 1
    except EOFError:
        logging.warning("Input buffer is empty!")
    except StopIteration:
        pass

    if instr_counter >= limit:
        logging.warning("Limit exceeded!")
    logging.info("output_buffer: %s", repr("".join(data_path.output_buffer)))
    return "".join(data_path.output_buffer), instr_counter, control_unit.current_tick()


def main(code_file: str, input_file: str):
    """Функция запуска модели процессора. Параметры -- имена файлов с машинным
    кодом и с входными данными для симуляции.
    """
    code = read_code(code_file)
    with open(input_file, encoding="utf-8") as file:
        input_text = file.read().strip()
        if not input_text:
            input_tokens = []
        else:
            input_tokens = eval(input_text)

    output, instr_counter, ticks = simulation(code, input_tokens=input_tokens, data_memory_size=100, limit=10000)

    print("".join(output))
    print("instr_counter: ", instr_counter, "ticks:", ticks)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    assert len(sys.argv) == 3, "Wrong arguments: machine.py <code_file> <input_file>"
    _, code_file, input_file = sys.argv
    main(code_file, input_file)
