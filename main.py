###########
version = '7.1'
## Input pins wired with PULL_DOWN
## Mid-stop = 0 to disable
## Add read amperage and temperature
## LCD 4 lines by 20 charaters
##########

from machine import Pin, I2C, ADC, Timer
import machine
import utime
import ujson
#import micropython
import gc
from lcd_api import LcdApi
from pico_i2c_lcd import I2cLcd
from math import sqrt

### default times if not config file not found
filename = 'harmonie_config.json'
config = {
    'Timers'        :   {
        'Opn1'      : 5,
        'Cls'       : 5,
        'Mid'       : 6,
        'Opn2'      : 8
    },
    'Current'       :   {
        'Status'    : 'Active',
        'N_lectures'      : 5,
        'V_max'     : 3.3,
        'V0_ref'    : 1.512,
        'Factor'    : 60
    },
    'Temp'          :   {
        'Status'    : 'Inactive',
        'V_max'     : 3.3,
        'V0_ref'    : 0.5,
        'Factor'    : 10
    }
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
prog_mode_delay = 2      # delay for press and hold before entre prog mode
press_duration = 500     # in ms, simulate duration of presssing a button
counter_readPin = 1      # How many times pins are read to determine good signal
delay_readPin = 1        # delay between each iteration to read pin

### menu
menu = ["Minuterie", "Courant", "Temperature", "ChavTha", "Dan", "Manaras", "Harmonie"]
menu_current_line = 1
menu_current_level = 0
menu_shift = 0
menu_total_lines = min(I2C_NUM_ROWS, len(menu))

Timers = {}
Current = {}
Temp = {}

def load_file(file):
    """Load json file configuration."""
    global Timers, Current, Temp
    with open(file, 'r') as infile:
        data = ujson.load(infile)
        Timers = data['Timers']
        Current = data['Current']
        Temp = data['Temp']

def write_file(file):
    """write config to file"""
    with open(file, 'w') as outfile:
        ujson.dump(config, outfile)

def initialize():
    """initialization before each run"""
    global state
    global stop_request
    global is_running
    global in_prog_mode
    global menu_current_line, menu_shift, menu_current_level
    
    state = 0
    menu_current_line = menu_shift = menu_current_level = 0
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
    lcd.write_line_center("HARMONIE V " + str(version), 1)
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
    if Current['Status'] == 'Active':
        current_timer.init(freq=2 , mode=Timer.PERIODIC, callback=read_current)

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
    
    counter = 0
    voltage = 0
    
    for _ in range(Current['N_lectures']):
        voltage += current_sensor.read_u16()
        utime.sleep_us(10)
    
    voltage = voltage / Current['N_lectures']
    
    amp = (voltage * Current['V_max']/65535  - Current['V0_ref']) * (1000/Current['Factor'])
    #amp = (max_voltage * Current['V_max']/65535 - 0.0245 - Current['V0_ref']) 
    lcd.write_line_center("I DC: {0:>5.1f} A".format(amp), 3) 

def read_temp():
    """Read temperature"""
     
    voltage = (Temp['V_max']/65535) * temp_sensor.read_u16()
    temp = (voltage - Temp['V0_ref']) * (1000/Temp['Factor'])
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
                
                if Temp['Status'] == 'Active':
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
    

def rotary_switch():
    """Rotary encoder to rotate left, right or select in menu."""

    previous_value = False
    result = ''
    
    while not Input['Prog'].value():
        if previous_value != Input['Down'].value():
            previous_value = Input['Down'].value()
            if Input['Down'].value() == False:
                if Input['Up'].value() == False:
                    # Going clockwise
                    print ('Rotary Next')
                    return 'Next'
                else:
                    # Going counter-clockwise
                    print('Rotary Previous')
                    return 'Previous'
    return 'Select'


def Config_Timers():
    """Configuration for timers open/close and mid-stop"""
    
    global menu_current_level, Timers, config
    is_value_modified = False
    
    menu_current_level = 2
    
    TimersItems = iter(Timers.items())
    key, value = next(TimersItems)
    blank_space = ' ' if len(key) <= 3 else ''
    
    lcd.clear()
    
    while not stop_request:
        try:
            if rotary_switch() == 'Select':
                if is_value_modified:
                    Timers.update({key : value})
                    config['Timers'] = Timers
                    write_file(filename)
                    load_file(filename)
                    is_value_modified = False
                    
                key, value = next(TimersItems)
                blank_space = ' ' if len(key) <= 3 else ''
                
            elif rotary_switch() == 'Next':
                value += 1
                if value > 999:
                    value = 0
                is_value_modified = True
                
            elif rotary_switch() == 'Previous':
                value -= 1
                if value < 0:
                    value = 999
                is_value_modified = True
                
            print('Timers')
            
            utime.sleep_ms(5)
            lcd.write_line_center("{0}{1}:{2:>3}".format(key.upper(), blank_space, value),  2)
                
        except StopIteration:
            TimersItems = iter(Timers.items())
        
    
def Config_Current():
    """Configuration for current sensor."""
    
    global Current, config
    is_value_modified = False
    
    CurrentItems = iter(Current.items())
    key, value = next(CurrentItems)
    blank_space = ' ' if len(key) <= 3 else ''
    format_str = ''
    
    lcd.clear()
    
    while not stop_request:
        try:
            if readPin('Prog'):
                if is_value_modified:
                    Current.update({key: value})
                    config['Current'] = Current
                    write_file(filename)
                    load_file(filename)
                    is_value_modified = False
                
                key, value = next(CurrentItems)
                blank_space = ' ' if len(key) <= 3 else ''
                
                if key == 'Status':
                    format_str = "{2:<8}"
                    lcd.clear_line(3)
                elif key == 'Factor':
                    format_str = "{2:<8}"
                    lcd.write_line_center('xyz mV/A', 3)
                elif key == 'N_lectures':
                    format_str = "{2:<8}"
                    lcd.write_line_center('Nbre de lectures', 3)
                elif key  in ['V_max', 'V0_ref']:
                    format_str = "{2:<8.3f}"
                    lcd.clear_line(3)
                else:
                    lcd.clear_line(3)
                
            elif readPin('Up'):
                if key == 'Status':
                    value = 'Active' if value == 'Inactive' else 'Inactive'
                elif key in ['Factor', 'N_lectures']:
                    value += 1
                elif key in ['V_max', 'V0_ref']:
                    value += 0.001
                    
                is_value_modified = True
            elif readPin('Down'):
                if key == 'Status':
                    value = 'Active' if value == 'Inactive' else 'Inactive'
                elif key in ['Factor', 'N_lectures']:
                    value -= 1 if int(value) >=1 else 0
                elif key in ['V_max', 'V0_ref']:
                    value -= 0.001 if float(value) >= 0.001 else 0
                    
                is_value_modified = True
            
            lcd.write_line_center(("{0:>6}{1}: " +format_str).format(key.upper(), blank_space, value),  2)
            utime.sleep_ms(10)
            
        except StopIteration:
            CurrentItems = iter(Current.items())
        

def Config_Temp():
    """Configuration for temperature."""
    global Temp, config
    is_value_modified = False
    
    TempItems = iter(Temp.items())
    key, value = next(TempItems)
    blank_space = ' ' if len(key) <= 3 else ''
    format_str = ''
    
    lcd.clear()
    
    while not stop_request:
        try:
            if readPin('Prog'):
                if is_value_modified:
                    Temp.update({key: value})
                    config['Temp'] = Temp
                    write_file(filename)
                    load_file(filename)
                    is_value_modified = False
                
                key, value = next(TempItems)
                blank_space = ' ' if len(key) <= 3 else ''
                
                if key in ['Status', 'Type']:
                    format_str = "{2:<8}"
                    lcd.clear_line(3)
                elif key == 'Factor':
                    format_str = "{2:<8}"
                    lcd.write_line_center('xyz mV/Degre', 3)
                elif key  in ['V_max', 'V0_ref']:
                    format_str = "{2:<8.3f}"
                    lcd.clear_line(3)
                else:
                    lcd.clear_line(3)
                
            elif readPin('Up'):
                if key == 'Status':
                    value = 'Active' if value == 'Inactive' else 'Inactive'
                elif key == 'Factor':
                    value += 1
                elif key in ['V_max', 'V0_ref']:
                    value += 0.01
                    
                is_value_modified = True
            elif readPin('Down'):
                if key == 'Status':
                    value = 'Active' if value == 'Inactive' else 'Inactive'
                elif key == 'Factor':
                    value -= 1 if int(value) >= 1 else 0
                elif key in ['V_max', 'V0_ref']:
                    value -= 0.01 if float(value) >= 0.01 else 0
                    
                is_value_modified = True
            
            lcd.write_line_center(("{0:>6}{1}: " +format_str).format(key.upper(), blank_space, value),  2)
            utime.sleep_ms(5)
            
        except StopIteration:
            TempItems = iter(Temp.items())
    
def Chavtha():
    lcd.clear()
    lcd.write_line_center("ha ha ha", 1)
    lcd.write_line_center("HA HA HA", 2)
    
def Dan():
    lcd.clear()
    lcd.write_line_center("Je veux 2 millions $".upper(), 2)
    
def Manaras():
    lcd.clear()
    lcd.write_line_center("Manaras", 2)

def Harmonie():
    lcd.clear()
    lcd.write_line_center("Harmonie", 2)
    
menu_fct = [Config_Timers, Config_Current, Config_Temp, Chavtha, Dan, Manaras, Harmonie]

def show_menu(menu_list, pos = 5):
    """Show menu on lcd"""
    
    line = 1
    lcd.clear()
                
    for item in menu_list:
        if menu_current_line == line:
            lcd.write_line('>>', line, 2)
        lcd.write_line(item.upper(), line, pos)
        line += 1

def Configuration():
    
    global in_prog_mode, menu_current_line, menu_shift, menu_current_level
    
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
        
    show_menu(menu[menu_shift:menu_shift + menu_total_lines])
    
    while in_prog_mode and not stop_request:
        
        if readPin('Up') or readPin('Down'):
            menu_current_level = 1
            if readPin('Up'):
                if menu_current_line < menu_total_lines:
                    menu_current_line += 1
                elif menu_shift + menu_total_lines < len(menu):
                    menu_shift += 1
            elif readPin('Down'):
                if menu_current_line == 0:
                    menu_current_line = 1
                elif menu_current_line > 1:
                    menu_current_line -= 1
                elif menu_shift > 0 :
                    menu_shift -= 1
            show_menu(menu[menu_shift:menu_shift + menu_total_lines])
            utime.sleep_ms(10)
            
        if readPin('Prog') and menu_current_level ==  1 :
            menu_fct[menu_shift + menu_current_line-1]()
        
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
        load_file(filename)
    
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
       
