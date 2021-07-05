# The MIT License (MIT)
# Copyright (c) 2020 Mike Teachman
# https://opensource.org/licenses/MIT

# Platform-independent MicroPython code for the rotary encoder module

# Documentation:
#   https://github.com/MikeTeachman/micropython-rotary

from machine import Pin
from micropython import const
from utime import sleep, sleep_ms, sleep_us

# Rotary Encoder States
_DIR_CW = const(0x10)  # Clockwise step
_DIR_CCW = const(0x20)  # Counter-clockwise step

_R_START = const(0x0)
_R_CW_1 = const(0x1)
_R_CW_2 = const(0x2)
_R_CW_3 = const(0x3)
_R_CCW_1 = const(0x4)
_R_CCW_2 = const(0x5)
_R_CCW_3 = const(0x6)
_R_ILLEGAL = const(0x7)

# _transition_table = [
# 
#     # |------------- NEXT STATE -------------|            |CURRENT STATE|
#     # CLK/DT    CLK/DT     CLK/DT    CLK/DT
#     #   00        01         10        11
#     [_R_START, _R_CCW_1, _R_CW_1,  _R_START],             # _R_START
#     [_R_CW_2,  _R_START, _R_CW_1,  _R_START],             # _R_CW_1
#     [_R_CW_2,  _R_CW_3,  _R_CW_1,  _R_START],             # _R_CW_2
#     [_R_CW_2,  _R_CW_3,  _R_START, _R_START | _DIR_CW],   # _R_CW_3
#     [_R_CCW_2, _R_CCW_1, _R_START, _R_START],             # _R_CCW_1
#     [_R_CCW_2, _R_CCW_1, _R_CCW_3, _R_START],             # _R_CCW_2
#     [_R_CCW_2, _R_START, _R_CCW_3, _R_START | _DIR_CCW],  # _R_CCW_3
#     [_R_START, _R_START, _R_START, _R_START]]             # _R_ILLEGAL

_transition_table_half_step = [
    [_R_CW_3,            _R_CW_2,  _R_CW_1,  _R_START],
    [_R_CW_3 | _DIR_CCW, _R_START, _R_CW_1,  _R_START],
    [_R_CW_3 | _DIR_CW,  _R_CW_2,  _R_START, _R_START],
    [_R_CW_3,            _R_CCW_2, _R_CCW_1, _R_START],
    [_R_CW_3,            _R_CW_2,  _R_CCW_1, _R_START | _DIR_CW],
    [_R_CW_3,            _R_CCW_2, _R_CW_3,  _R_START | _DIR_CCW]]

_STATE_MASK = const(0x07)
_DIR_MASK = const(0x30)

class Rotary:

    def __init__(self, sw_pin, clk_pin, dt_pin):
        self._sw_pin = Pin(sw_pin, Pin.IN, Pin.PULL_DOWN)
        self._clk_pin = Pin(clk_pin, Pin.IN, Pin.PULL_DOWN)
        self._dt_pin = Pin(dt_pin, Pin.IN, Pin.PULL_DOWN)
        self._select = False
        self._value = 0
        self._state = _R_START
    
    def reset(self):
        self._value = 0

    def select(self):
        self._select = True if self._sw_pin.value() else False
        return self._select
    
    def value(self):
        clk_dt_pin = (self._clk_pin.value() << 1) | self._dt_pin.value() 
        self._state = _transition_table_half_step[self._state & _STATE_MASK][clk_dt_pin]
        direction = self._state & _DIR_MASK
 
        incr = 0
        # incr value found by trial and error
        if direction == _DIR_CW:
            incr = 1
        elif direction == _DIR_CCW:
            incr = -1
            
        return incr
    
########## END OF CLASS ################

def main():
    
    rotary_sw = Rotary(
    sw_pin = 9,     # select bouton
    clk_pin = 7,    # signal A
    dt_pin = 8      # signal B
    )
    
    counter = 0
    while counter <= 10:
        sw_value = rotary_sw.value()
        if sw_value != 0:
            print("{:>5} {:>2}".format(counter, sw_value))
            counter += 1
            sleep_ms(500)
        sleep_ms(10)

if __name__ == '__main__':
    main()