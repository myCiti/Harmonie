import machine as m
import utime
import ujson
import _thread
from lcd_api import LcdApi
from pico_i2c_lcd import I2cLcd

### default times if not config file not found
filename = 'timer_config.json'
Timers = {
    'Opn1' : 5,
    'Opn2' : 5,
    'Cls'  : 10,
    'Mid'  : 9
    }

### input pins
inputPin = {
    "Open"     : 21,
    "Close"    : 20,
    "Stop"     : 19,
    "OpenLmt"  : 27,
    "CloseLmt" : 26,
    "Prog"     : 13,
    "Up"       : 14,
    "Down"     : 15
    }

outputPin = {
    "Open"     : 17,
    "Close"    : 16,
    "Stop"     : 16
    }

Input = {}
Output = {}

### LCD config
I2C_ADDR     = 0x27
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16
i2c = m.I2C(0, sda=m.Pin(0), scl=m.Pin(1), freq=400000)
lcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)  

### some global variables
state = 0
stop_request = False
is_running = False
in_prog_mode = False
prog_mode_delay = 3      # delay for press and hold before entre prog mode
press_duration = 100     # in ms, simulate duration of presssing a button

for p in inputPin:
    Input[p] = m.Pin(inputPin[p], m.Pin.IN)

for p in outputPin:
    Output[p] = m.Pin(outputPin[p], m.Pin.OUT)

# try:
#     with open(filename) as infile:
#         data = ujson.load(infile)
#         for p in data:
#             Timers[p] = data[p]
# except OSError:
#     with open(filename, 'w') as outfile:
#         ujson.dump(Timers, outfile)

def load_file(file):
    """Load json file configuration."""
    global Timers
    with open(file) as infile:
        data = ujson.load(infile)
        for p in data:
            Timers[p] = data[p]

def write_file(file):
    """write config to file"""
    with open(file, 'w') as outfile:
        ujson.dump(Timers, outfile)

def initialize():
    """initialization before each run"""
    global state
    global stop_request
    global is_running
    global in_prog_mode
    
    state = 0
    stop_request = False
    is_running = False
    in_prog_mode = False
    
    for p in Output:
        Output[p].value(0)
        
    lcd.clear()
    lcd.write_line_center("HARMONIE", 1)
    lcd.write_line_center("BIENVENUE", 2)
    utime.sleep(2)
    lcd.clear()
    lcd.write_line("Cls:{0:<3},Opn1:{1:<3}".format(Timers['Cls'], Timers['Opn1']), 1)
    lcd.write_line("Mid:{0:<3},Opn2:{1:<3}".format(Timers['Mid'], Timers['Opn2']), 2)
    
def writePin(pin, pause):
    """Write high value to pin, pause in ms"""
    if not stop_request:
        Output[pin].value(1)
        utime.sleep_ms(pause)
        Output[pin].value(0)
        if pin == 'Open':
            lcd.clear()
            lcd.write_line_center("EN OUVERTURE ", 1)
        else:
            lcd.clear()
            lcd.write_line_center("EN FERMETURE ", 1)

def lcd_count_down(duration):
    """count down in second"""
    global stop_request
    for i in reversed(range(1, duration+1)):
        lcd.write_line("{0:2}".format(i), 2, 13)
        if stop_request:
            break
        utime.sleep(1)

def stop_signal_handler(pin):
    """Send stop_request when activate"""
    #Input['Stop'].irq(handler=None)
    global stop_request
    stop_request = True
    Input['Stop'].irq(handler=stop_signal_handler)
    #while True:
    #   if Input['Stop'].value():
    #        stop_request = True
    #        m.enable_irq()

def Logic_loop():
    """The main state logic. Core program"""
    global state
    global stop_request
    global is_running
    
    is_running = True
    
    while not stop_request:
        
        if state == 0:              # initial state
            if Input['Close'].value():
                writePin('Close', press_duration)
                state = 1
            elif Input['Open'].value():
                writePin('Open', press_duration)
                state = 2
        elif state == 1:            # door fully closed, close limit triggers
            if Input['CloseLmt'].value():
                lcd.clear()
                lcd.write_line_center("PORTE FERMEE", 1)
                lcd.write_line("OUVERTURE:", 2, 2)
                lcd_count_down(Timers['Cls'])
                writePin('Open', press_duration)
                state = 2
        elif state == 2:            # door fully opened, before mid-stop
            if Input['OpenLmt'].value():
                lcd.clear()
                lcd.write_line_center("PORTE OUVERTE", 1)
                lcd.write_line("FERMETURE:", 2, 2)
                lcd_count_down(Timers['Opn1'])
                writePin('Close', press_duration)
                state = 3
        elif state == 3:             # mi-stop
            lcd.clear()
            lcd.write_line_center("MI-ARRET", 1)
            lcd.write_line("OUVERTURE:", 2, 2)
            lcd_count_down(Timers['Mid'])
            writePin('Open', press_duration)
            state = 4
        elif state == 4:              # door fully opened, after mid-stop
            if Input['OpenLmt'].value():
                lcd.clear()
                lcd.write_line_center("PORTE OUVERTE", 1)
                lcd.write_line("FERMETURE:", 2, 2)
                lcd_count_down(Timers['Opn2'])
                writePin('Close', press_duration)
                state = 1
        else:
            print("ERREUR")
        #gc.collect()
        #gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

def change_timers():
    global in_prog_mode
    global Timers
    # press and hold to enter into programming mode
    hold_counter = 0

    while True:
        if hold_counter >= prog_mode_delay :
            in_prog_mode = True
            lcd.clear()
            lcd.write_line_center("PROG: MINUTERIE", 1)
            break
        elif Input['Prog'].value():
            hold_counter += 1
        else:
            hold_counter = 0
        utime.sleep(1)
    
    #utime.sleep(1)
    if in_prog_mode:
        iterTimers = iter(Timers.items())
        is_timers_changed = False
        while not Input['Stop'].value():
            try:
                if Input['Prog'].value():
                    if is_timers_changed:
                        Timers.update({key : value})
                        write_file(filename)
                        load_file(filename)
                        is_timers_changed = False
                        
                    key, value = next(iterTimers)
                    space = ' :' if len(key) <= 3 else ':'
                    lcd.write_line(key + space, 2, 1)
                    lcd.write_line("{0:<5}".format(value), 2, 7)
                    utime.sleep_ms(500)
                while Input['Up'].value():
                    value += 1
                    lcd.write_line("{0:<5}".format(value), 2, 7)
                    is_timers_changed = True
                    utime.sleep_ms(300)
                while Input['Down'].value():
                    value -= 1
                    is_timers_changed = True
                    if value <= 0:
                        value = 0
                    lcd.write_line("{0:<5}".format(value), 2, 7)
                    utime.sleep_ms(300)
            except StopIteration:
                iterTimers = iter(Timers.items())

# initialize before first run
initialize()

def main():
    """Main program, call others functions"""
    #global state
    global stop_request
    global is_running
    global in_prog_mode
    
    try:
        load_file(filename)
    except OSError:
        write_file(filename)
    
    #_thread.start_new_thread(stop_signal_handler, ())
    
    while True:
        if not is_running:
            if Input['Close'].value() or Input['Open'].value():
                Logic_loop()
            elif Input['Prog'].value():
                change_timers()
        if stop_request:
            initialize()
            

# listen to Stop interrupt
Input['Stop'].irq(trigger=m.Pin.IRQ_RISING, handler=stop_signal_handler)

if __name__ == '__main__':
    main()
    #change_timers()
       
## test file
#for p in config:
#    print(str(p) + ':' + str(config[p]))
