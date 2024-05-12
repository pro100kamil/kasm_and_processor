#!/usr/bin/python3
"""Модель процессора, позволяющая выполнить машинный код полученный из программы
на языке Brainfuck.

Модель включает в себя три основных компонента:

- `DataPath` -- работа с памятью данных и вводом-выводом.

- `ControlUnit` -- работа с памятью команд и их интерпретация.

- и набор вспомогательных функций: `simulation`, `main`.
"""

import logging
import sys

from isa import Opcode, read_code


class Memory:
    def __init__(self, data_memory_size: int, code: list):
        # data_memory_size = 100
        self.shift = data_memory_size
        self.memory = [0] * data_memory_size + code


class ALU:
    def calc(self, sel: Opcode, l, r):
        return {
            Opcode.INC: l + 1,
            Opcode.DEC: l - 1,
            Opcode.MOV: l,
            Opcode.ADD: l + r,
            Opcode.SUB: l - r,
            Opcode.MOD: l % r if r != 0 else None,
            Opcode.MUL: l * r,
        }.get(sel.value)


class DataPath:
    """Тракт данных (пассивный), включая: ввод/вывод, память и арифметику.

    ```text
     latch --------->+--------------+  addr   +--------+
     data            | data_address |---+---->|  data  |
     addr      +---->+--------------+   |     | memory |
               |                        |     |        |
           +-------+                    |     |        |
    sel -->|  MUX  |         +----------+     |        |
           +-------+         |                |        |
            ^     ^          |                |        |
            |     |          |        data_in |        | data_out
            |     +---(+1)---+          +---->|        |-----+
            |                |          |     |        |     |
            +---------(-1)---+          |  oe |        |     |
                                        | --->|        |     |
                                        |     |        |     |
                                        |  wr |        |     |
                                        | --->|        |     |
                                        |     +--------+     |
                                        |                    v
                                    +--------+  latch_acc +-----+
                          sel ----> |  MUX   |  --------->| acc |
                                    +--------+            +-----+
                                     ^   ^  ^                |
                                     |   |  |                +---(==0)---> zero
                                     |   |  |                |
                                     |   |  +---(+1)---------+
                                     |   |                   |
                                     |   +------(-1)---------+
                                     |                       |
            input -------------------+                       +---------> output
    ```

    - data_memory -- однопортовая, поэтому либо читаем, либо пишем.

    - input/output -- токенизированная логика ввода-вывода. Не детализируется в
      рамках модели.

    - input -- чтение может вызвать остановку процесса моделирования, если буфер
      входных значений закончился.

    Реализованные методы соответствуют сигналам защёлкивания значений:

    - `signal_latch_data_addr` -- защёлкивание адреса в памяти данных;
    - `signal_latch_acc` -- защёлкивание аккумулятора;
    - `signal_wr` -- запись в память данных;
    - `signal_output` -- вывод в порт.

    Сигнал "исполняется" за один такт. Корректность использования сигналов --
    задача `ControlUnit`.
    """

    # data_memory_size = None
    # "Размер памяти данных."

    # data_memory = None
    # "Память данных. Инициализируется нулевыми значениями."
    memory = None

    alu = None

    data_address = None
    "Адрес в памяти данных. Инициализируется нулём."

    buffer = None
    "Буферный регистр. Инициализируется нулём."

    acc = None
    "Аккумулятор. Инициализируется нулём."

    input_buffer = None
    "Буфер входных данных. Инициализируется входными данными конструктора."

    output_buffer = None
    "Буфер выходных данных."

    registers = {"acc": 0,
                 "rc": 0,
                 "rs": 0,
                 "r1": 0,
                 "r2": 0,
                 "r3": 0,
                 "r7": 0}

    def __init__(self, alu: ALU, memory: Memory, input_buffer: list):
        # assert data_memory_size > 0, "Data_memory size should be non-zero"
        # self.data_memory_size = data_memory_size
        # self.data_memory = [0] * data_memory_size
        self.memory = memory
        self.alu = alu
        self.data_address = 0
        self.acc = 0
        self.buffer = 0
        self.input_buffer = input_buffer
        self.output_buffer = []

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
        elif sel == Opcode.RIGHT.value:
            self.data_address += 1

        assert 0 <= self.data_address < len(self.memory.memory), "out of memory: {}".format(self.data_address)

    def signal_latch_acc(self):
        """Защёлкнуть слово из памяти (`oe` от Output Enable) и защёлкнуть его в
        аккумулятор. Сигнал `oe` выставляется неявно `ControlUnit`-ом.
        """
        self.acc = self.memory.memory[self.data_address]

    def calc(self, sel, l, r):
        res = self.alu.calc(sel, l, r)
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

        >>> dp = DataPath(ALU(), Memory(100, []), [chr(127)])
        >>> dp.signal_wr(Opcode.INPUT.value)
        >>> dp.signal_latch_acc()
        >>> dp.acc
        127
        >>> dp.signal_wr(Opcode.INC.value)
        >>> dp.signal_latch_acc()
        >>> dp.acc
        -128

        """
        assert sel in {
            Opcode.INC.value,
            Opcode.DEC.value,
            Opcode.INPUT.value,
        }, "internal error, incorrect selector: {}".format(sel)

        if sel == Opcode.INC.value:
            self.memory.memory[self.data_address] = self.acc + 1
            if self.memory.memory[self.data_address] == 128:
                self.memory.memory[self.data_address] = -128
        elif sel == Opcode.DEC.value:
            self.memory.memory[self.data_address] = self.acc - 1
            if self.memory.memory[self.data_address] == -129:
                self.memory.memory[self.data_address] = 127
        elif sel == Opcode.INPUT.value:
            if len(self.input_buffer) == 0:
                raise EOFError()
            symbol = self.input_buffer.pop(0)
            symbol_code = ord(symbol)
            assert -128 <= symbol_code <= 127, "input token is out of bound: {}".format(symbol_code)
            self.memory.memory[self.data_address] = symbol_code
            logging.debug("input: %s", repr(symbol))

        elif sel == Opcode.ADD.value:
            self.memory.memory[self.data_address] = self.acc + self.buffer
            if self.memory.memory[self.data_address] >= 128:
                self.memory.memory[self.data_address] = -128 + self.memory.memory[self.data_address] % 256
        elif sel == Opcode.MOD.value:
            self.memory.memory[self.data_address] = self.acc % self.buffer

    def signal_output(self):
        """Вывести значение аккумулятора в порт вывода.

        Вывод осуществляется путём конвертации значения аккумулятора в символ по
        ASCII-таблице.
        """
        symbol = chr(self.acc)
        logging.debug("output: %s << %s", repr("".join(self.output_buffer)), repr(symbol))
        self.output_buffer.append(symbol)

    def zero(self):
        """Флаг нуля. Необходим для условных переходов."""
        return self.acc == 0


class ControlUnit:
    """Блок управления процессора. Выполняет декодирование инструкций и
    управляет состоянием модели процессора, включая обработку данных (DataPath).

    Согласно варианту, любая инструкция может быть закодирована в одно слово.
    Следовательно, индекс памяти команд эквивалентен номеру инструкции.

    ```text
    +------------------(+1)-------+
    |                             |
    |   +-----+                   |
    +-->|     |     +---------+   |    +---------+
        | MUX |---->| program |---+--->| program |
    +-->|     |     | counter |        | memory  |
    |   +-----+     +---------+        +---------+
    |      ^                               |
    |      | sel_next                      | current instruction
    |      |                               |
    +---------------(select-arg)-----------+
           |                               |      +---------+
           |                               |      |  step   |
           |                               |  +---| counter |
           |                               |  |   +---------+
           |                               v  v        ^
           |                       +-------------+     |
           +-----------------------| instruction |-----+
                                   |   decoder   |
                                   |             |<-------+
                                   +-------------+        |
                                           |              |
                                           | signals      |
                                           v              |
                                     +----------+  zero   |
                                     |          |---------+
                                     | DataPath |
                      input -------->|          |----------> output
                                     +----------+
    ```

    """

    # program = None
    # "Память команд."

    program_counter = None
    "Счётчик команд. Инициализируется сдвигом, потому что данные лежат до команд."

    data_path = None
    "Блок обработки данных."

    _tick = None
    "Текущее модельное время процессора (в тактах). Инициализируется нулём."

    def __init__(self, memory: Memory, data_path: DataPath):
        # self.program = program
        self.memory = memory
        self.program_counter = memory.shift
        self.data_path = data_path
        self._tick = 0

    def tick(self):
        """Продвинуть модельное время процессора вперёд на один такт."""
        self._tick += 1

    def current_tick(self):
        """Текущее модельное время процессора (в тактах)."""
        return self._tick

    def signal_latch_program_counter(self, sel_next):
        """Защёлкнуть новое значение счётчика команд.

        Если `sel_next` равен `True`, то счётчик будет увеличен на единицу,
        иначе -- будет установлен в значение аргумента текущей инструкции.
        """
        if sel_next:
            self.program_counter += 1
        else:
            instr = self.memory.memory[self.program_counter]
            assert "arg" in instr, "internal error"
            self.program_counter = instr["arg"][0]

    def decode_and_execute_control_flow_instruction(self, instr, opcode, phase):
        """Декодировать и выполнить инструкцию управления потоком исполнения. В
        случае успеха -- вернуть `True`, чтобы перейти к следующей инструкции.
        """
        if opcode is Opcode.HALT:
            raise StopIteration()

        if opcode is Opcode.JMP:
            addr = instr["arg"]
            self.program_counter = addr
            self.tick()

            return True

        if opcode is Opcode.JZ:
            addr, reg = instr["arg"]

            # if phase == 1:
            #     self.data_path.signal_latch_acc()
            #     self.tick()
            #     return None
            # elif phase == 2:
            #     if self.data_path.zero():
            #         self.signal_latch_program_counter(sel_next=False)
            #     else:
            #         self.signal_latch_program_counter(sel_next=True)
            #     self.tick()
            #
            #     return True

            if self.data_path.registers.get(reg) == 0:
                self.signal_latch_program_counter(sel_next=False)
            else:
                self.signal_latch_program_counter(sel_next=True)
            self.tick()

            return True

        if opcode is Opcode.JNZ:
            addr, reg = instr["arg"]

            if self.data_path.registers.get(reg) != 0:
                self.signal_latch_program_counter(sel_next=False)
            else:
                self.signal_latch_program_counter(sel_next=True)
            self.tick()

            return True

        return False

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
        instr = self.memory.memory[self.program_counter]
        opcode = instr["opcode"]

        res = self.decode_and_execute_control_flow_instruction(instr, opcode, phase)
        if res is None:
            return None
        if res:
            return True  # True, если мы полностью выполнили инструкцию

        if opcode in {Opcode.RIGHT, Opcode.LEFT}:
            self.data_path.signal_latch_data_addr(opcode.value)
            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        elif opcode in {Opcode.INC, Opcode.INPUT}:
            if phase == 1:
                self.data_path.signal_latch_acc()
                self.tick()
                return None
            elif phase == 2:
                self.data_path.signal_wr(opcode.value)
                self.signal_latch_program_counter(sel_next=True)
                self.tick()
                return True
            # if phase == 1:
            #     self.data_path.signal_latch_acc()
            #     self.tick()
            #     return None
            # elif phase == 2:
            #     self.data_path.buffer = instr["arg"]
            #
            #     self.data_path.signal_wr(opcode.value)
            #     self.signal_latch_program_counter(sel_next=True)
            #     self.tick()
            #     return True

        elif opcode is Opcode.PRINT:
            if phase == 1:
                self.data_path.signal_latch_acc()
                self.tick()
                return None
            elif phase == 2:
                self.data_path.signal_output()
                self.signal_latch_program_counter(sel_next=True)
                self.tick()
                return True

        elif opcode == Opcode.MOV:
            # rn only reg = number
            args = instr["arg"]
            assert args[0] in self.data_path.registers, "unknown register"

            self.data_path.registers[args[0]] = int(args[1])

            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        elif opcode in {Opcode.MOD, Opcode.MUL, Opcode.ADD, Opcode.SUB}:
            args: list[str]
            args = instr["arg"]
            a, b, c = args
            assert a in self.data_path.registers, "unknown register"

            if b.isdigit():
                b = int(b)
            else:
                b = self.data_path.registers.get(b)

            if c.isdigit():
                c = int(c)
            else:
                c = self.data_path.registers.get(c)

            self.data_path.registers[a] = self.data_path.calc(instr["opcode"], b, c)

            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        elif opcode == Opcode.DEC:
            args = instr["arg"]
            a = args[0]
            assert a in self.data_path.registers, "unknown register"

            self.data_path.registers[a] -= 1

            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        elif opcode == Opcode.ADD_STR:
            self.memory.memory[self.program_counter] = self.data_path.data_address

            length, s = instr["arg"]

            length = int(length)
            s = s[1:-1]

            self.memory.memory[self.data_path.data_address] = length
            self.data_path.data_address += 1

            for i in range(length):
                self.memory.memory[self.data_path.data_address] = ord(s[i])
                self.data_path.data_address += 1

            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        elif opcode == Opcode.PRINT_STR:
            self.memory.memory[self.program_counter] = self.data_path.data_address

            addr = instr["arg"]
            addr_ = self.memory.memory[addr]

            length = self.memory.memory[addr_]
            self.data_path.data_address = addr_ + 1

            for i in range(length):
                self.data_path.signal_latch_acc()
                # self.tick()
                self.data_path.signal_output()
                self.data_path.data_address += 1
            # self.signal_latch_program_counter(sel_next=True)
            # self.tick()
            # return True

            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

        elif opcode in {Opcode.MOV, Opcode.MOD, Opcode.MUL, Opcode.ADD, Opcode.SUB, Opcode.JNZ}:
            arg = instr["arg"]
            # print(opcode, arg)
            self.signal_latch_program_counter(sel_next=True)
            self.tick()
            return True

    def __repr__(self):
        """Вернуть строковое представление состояния процессора."""
        state_repr = "TICK: {:3} PC: {:3} ADDR: {:3} MEM_OUT: {} ACC: {}".format(
            self._tick,
            self.program_counter,
            self.data_path.data_address,
            self.memory.memory[self.data_path.data_address],
            self.data_path.registers.get("rs"),
        )

        instr = self.memory.memory[self.program_counter]
        opcode = instr["opcode"]
        instr_repr = str(opcode)

        if "arg" in instr:
            instr_repr += " {}".format(instr["arg"])

        if "term" in instr:
            term = instr["term"]
            instr_repr += "  ('{}'@{}:{})".format(term.symbol, term.line, term.pos)

        return "{} \t{}".format(state_repr, instr_repr)


def simulation(code, input_tokens, data_memory_size, limit):
    """Подготовка модели и запуск симуляции процессора.

    Длительность моделирования ограничена:

    - количеством выполненных инструкций (`limit`);

    - количеством данных ввода (`input_tokens`, если ввод используется), через
      исключение `EOFError`;

    - инструкцией `Halt`, через исключение `StopIteration`.
    """
    memory = Memory(data_memory_size, code)
    alu = ALU()
    data_path = DataPath(alu, memory, input_tokens)
    control_unit = ControlUnit(memory, data_path)
    instr_counter = 0

    logging.debug("%s", control_unit)
    try:
        while instr_counter < limit:
            phase = 1
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


def main(code_file, input_file):
    """Функция запуска модели процессора. Параметры -- имена файлов с машинным
    кодом и с входными данными для симуляции.
    """
    code = read_code(code_file)
    with open(input_file, encoding="utf-8") as file:
        input_text = file.read()
        input_token = []
        for char in input_text:
            input_token.append(char)

    output, instr_counter, ticks = simulation(
        code,
        input_tokens=input_token,
        data_memory_size=100,
        limit=10000
    )

    print("".join(output))
    print("instr_counter: ", instr_counter, "ticks:", ticks)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    assert len(sys.argv) == 3, "Wrong arguments: machine.py <code_file> <input_file>"
    _, code_file, input_file = sys.argv
    main(code_file, input_file)
