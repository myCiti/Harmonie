###########
version = 0.6
## Input pins wired with PULL_DOWN
## Mid-stop = 0 to disable
## Add read amperage and temperature
## LCD 4 lines by 20 charaters
##########

from machine import Pin, I2C, ADC, Timer
import utime
import ujson
#import micropython
import gc
from lcd_api import LcdApi
from pico_i2c_lcd import I2cLcd
from math import sqrt

### default times if not config file not found
filename = 'harmonie_config.json'
Timers = {
    'Opn1' : 5,
    'Cls'  : 5,
    'Mid'  : 6,
    'Opn2' : 8
    }

### input pins
inPin = {
    "Open"     : 4,
    "Close"    : 5,
    "Stop"     : 6,
    "OpenLmt"  : 3,
    "CloseLmt" : 2,
    "Prog"     : 9,
    "Up"       : 8,
    "Down"     : 7
    }

outPin = {
    "Open"     : 10,
    "Close"    : 11,
    "Stop"     : 12,
    "Spare"    : 13
    }

Input = dict((name, Pin(pin, Pin.IN, Pin.PULL_DOWN)) for (name, pin) in inPin.items())
Output = dict((name, Pin(pin, Pin.OUT)) for (name, pin) in outPin.items())

### LCD config
I2C_ADDR     = 0x27
I2C_NUM_ROWS = 4
I2C_NUM_COLS = 20
i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
lcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)

current_sensor = ADC(1)    # read curent at ADC(0)
temp_sensor = ADC(2)      # read temperature at ADC(1)
machine.freq(133000000)   # set cpu frequency

current_timer = Timer()
temp_timer = Timer()

### some global variables
state = 0
stop_request = False
is_running = False
in_prog_mode = False
prog_mode_delay = 1      # delay for press and hold before entre prog mode
press_duration = 500     # in ms, simulate duration of presssing a button
counter_readPin = 1      # How many times pins are read to determine good signal
delay_readPin = 1        # delay between each iteration to read pin

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
        
    for p in Input:
        Input[p]        
    ## make sure that open after mid-top is 0 if no mid-stop
    Timers['Opn2'] = 0 if Timers['Mid'] == 0 else Timers['Opn2']
    
    current_timer.deinit()
    #temp_timer.deinit()
    
    lcd.clear()
    lcd.write_line_center("HARMONIE V" + str(version), 1)
    lcd.write_line_center("BIENVENUE", 2)
    utime.sleep(2)
    lcd.clear()
    lcd.write_line_center("Cls:{0:>3},Opn1:{1:>3}".format(Timers['Cls'], Timers['Opn1']), 1)
    lcd.write_line_center("Mid:{0:>3},Opn2:{1:>3}".format(Timers['Mid'], Timers['Opn2']), 2)   
    
def readPin(pin, counter = counter_readPin, delay = delay_readPin):
    """Read pin a number of times to determine good signal, delay in msec"""
    read_count = 0
    
    for i in range(counter):
        if Input[pin].value():
            read_count += 1
        utime.sleep_ms(delay)
            
    if read_count == counter:
        return True
    
    return False

def writePin(pin, delay):
    """Write high value to pin, pause in ms"""
    
    if not stop_request:
        if pin == 'Open' and Input['OpenLmt'].value() != 1:
            Output[pin].value(1)
            lcd.clear_line(1)
            lcd.clear_line(2)
            lcd.write_line_center("EN OUVERTURE ", 1)
        elif pin == 'Close' and Input['CloseLmt'].value() != 1:
            Output[pin].value(1)
            lcd.clear_line(1)
            lcd.clear_line(2)
            lcd.write_line_center("EN FERMETURE ", 1)
        
        utime.sleep_ms(delay)
        Output[pin].value(0)
    # start reading current
    current_timer.init(freq=4, mode=Timer.PERIODIC, callback=read_current)

def lcd_count_down(duration):
    """count down in second"""
    global stop_request
    msg = ''
    
    # stop reading current
    current_timer.deinit()
    
    if state == 1 or state == 3: # clsLmt activated, door will open
        msg = "OUVERTURE:"
    elif state == 2 or state == 4: # opnLmt activated, door will close
        msg = "FERMETURE:"
    
    for i in  range(duration, 0, -1):
        lcd.write_line_center("{0}{1:>3}".format(msg, i), 2)
        if stop_request:
            break
        elif state == 3 and Input['CloseLmt'].value():
            break
        utime.sleep(1)
    
    
def stop_signal_handler(pin):
    """Send stop_request when activate"""
    
    read_count = 0
    global stop_request
    current_timer.deinit()
    
    for i in range(counter_readPin):
        if Input['Stop'].value:
            read_count += 1
        utime.sleep_ms(delay_readPin)
        
    if read_count == counter_readPin: 
        stop_request = True
        Output['Stop'].value(1)
        utime.sleep_ms(press_duration)
        Output['Stop'].value(0)

def read_current(timer):
    """Read current in amp"""
    
    global stop_request
    
    conversion_factor = 3.3/65535
    sensitivity_factor = 10
    counter = 0
    max_voltage = 0
    voltage = 0
    voltage_ref = 1.685
    reading_duration_ms = 30
    start_time = utime.ticks_ms()

    while utime.ticks_diff(utime.ticks_ms(), start_time) < reading_duration_ms:
        voltage = current_sensor.read_u16()
        if max_voltage < voltage:
            max_voltage = voltage
        utime.sleep_us(50)
    amp = (max_voltage * conversion_factor - voltage_ref) * sensitivity_factor
    lcd.write_line_center("Courant:{0:>5.1f} A".format(amp), 3)


def read_temp():
    """Read temperature"""
    
    voltage = (3.3/65535) * temp_sensor.read_u16()
    temp = (voltage - 0.5) * 100
    lcd.write_line_center('Temp: {0:>5.1f} '.format(temp) + chr(223) + 'C', 4)

def Logic_loop():
    """The main state logic. Core program"""
    global state
    global stop_request
    global is_running
    
    is_running = True
    
    while not stop_request:
        
        if state == 0:              # initial state
            if readPin('Close'):
                writePin('Close', press_duration)
                state = 1
            elif readPin('Open'):
                writePin('Open', press_duration)
                state = 2
        elif state == 1:            # door fully closed, close limit triggers
            if readPin('CloseLmt'):
                current_timer.deinit()
                lcd.clear_line(1)
                lcd.clear_line(3)
                lcd.write_line_center("PORTE FERMEE", 1)
                read_temp()    # read and show temperature
                lcd_count_down(Timers['Cls'])
                writePin('Open', press_duration)
                state = 2
                gc.collect()        # force gc collection
                #print(gc.mem_free())
        elif state == 2:            # door fully opened, before mid-stop
            if readPin('OpenLmt'):
                current_timer.deinit()
                lcd.clear_line(1)
                lcd.clear_line(3)
                lcd.write_line_center("PORTE OUVERTE", 1)
                lcd_count_down(Timers['Opn1'])
                writePin('Close', press_duration)
                state = 1 if Timers['Mid'] == 0 else 3
        elif state == 3:             # mi-stop
            current_timer.deinit()
            lcd.clear_line(1)
            lcd.clear_line(3)
            lcd.write_line_center("MI-ARRET", 1)
            lcd_count_down(Timers['Mid'])
            writePin('Open', press_duration)
            state = 4
        elif state == 4:              # door fully opened, after mid-stop
            if readPin('OpenLmt'):
                current_timer.deinit()
                lcd.clear_line(1)
                lcd.clear_line(3)
                lcd.write_line_center("PORTE OUVERTE", 1)
                lcd_count_down(Timers['Opn2'])
                writePin('Close', press_duration)
                state = 1
        else:
            print("ERREUR")
        
def change_timers():
    global in_prog_mode
    global Timers
    # press and hold to enter into programming mode
    hold_counter = 0
    key = ''
    value = 0

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
        while not stop_request:
            try:
                if readPin('Prog'):
                    if is_timers_changed:
                        Timers.update({key : value})
                        write_file(filename)
                        load_file(filename)
                        is_timers_changed = False
                        
                    key, value = next(iterTimers)
                    space = ' :' if len(key) <= 3 else ':'
                    lcd.write_line(key + space, 2, 3)
                    lcd.write_line("{0:>3}".format(value), 2, 8)
                    utime.sleep_ms(300)
                while readPin('Up'):
                    value += 1
                    if value > 999:
                        value = 0
                    lcd.write_line("{0:>3}".format(value), 2, 8)
                    is_timers_changed = True
                    utime.sleep_ms(300)
                while readPin('Down'):
                    value -= 1
                    if value < 0:
                        value = 999
                    is_timers_changed = True
                    lcd.write_line("{0:>3}".format(value), 2, 8)
                    utime.sleep_ms(300)
            except StopIteration:
                iterTimers = iter(Timers.items())

current_line = 1
shift = 0
menu = ["Minuterie", "Voltage", "Temperateur", "ChavTha", "Dan", "Manaras", "Harmonie"]
#menu = ["Minuterie", "Voltage", "Temperateur"]
total_lines = min(I2C_NUM_ROWS, len(menu))

def show_menu():
    """Show menu on lcd"""
    
    line = 1
    short_list = menu[shift:shift + total_lines]
    
    lcd.clear()
    for item in short_list:
        if current_line == line:
            lcd.write_line('>>', line, 2)
        lcd.write_line(item.upper(), line, 5)
        line += 1

def Configuration():
    
    global in_prog_mode, current_line, shift, total_lines
    
    hold_counter = 0
 
    while True:
        if hold_counter >= prog_mode_delay :
            in_prog_mode = True
            lcd.clear()
            break
        elif readPin('Prog'):
            hold_counter += 1
        else:
            hold_counter = 0
        utime.sleep(1)
        
    show_menu()
    while in_prog_mode and not stop_request:
        
        if readPin('Up') or readPin('Down'):
            if readPin('Up'):
                if current_line < total_lines:
                    current_line += 1
                elif shift + total_lines < len(menu):
                    shift += 1
            elif readPin('Down'):
                if current_line > 1:
                    current_line -= 1
                elif shift > 0 :
                    shift -= 1
        
            show_menu()
        utime.sleep_ms(100)
        

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
    
    initialize()
    
    #_thread.start_new_thread(stop_signal_handler, ())
    
    while True:
        if not is_running:
            if readPin('Close') or readPin('Open'):
                Logic_loop()
            elif readPin('Prog'):
                Configuration()
        if stop_request:
            initialize()
            

# listen to Stop interrupt
Input['Stop'].irq(trigger=Pin.IRQ_RISING, handler=stop_signal_handler)


if __name__ == '__main__':
    main()
    #change_timers()
       
