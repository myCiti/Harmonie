###########
version = '7.5'
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
from menu import Menu
from rotary_enc import Rotary
from math import sqrt

### default times if not config file not found
filename = 'harmonie_config.json'
config = {
    'Timers'        :   {
        'Opn1'      : 3,
        'Cls'       : 2,
        'Mid'       : 4,
        'Opn2'      : 2
    },
    'Current'       :   {
        'Statut'    : 'Active',
        'N_lect'      : 5,
        'V_max'     : 3.3,
        'V0_ref'    : 1.512,
        'Fcteur'    : 60
    },
    'Temp'          :   {
        'Statut'    : 'Inactiv',
        'V_max'     : 3.3,
        'V0_ref'    : 0.5,
        'Fcteur'    : 10
    },
    'Parametres'    :  {
        'LCD_li'    : 4,
        'LCD_co'    : 20,
        'Compteur'  : 'ClsLmt',
        'btn_dura'    : 100,
        'btn_lect'    : 2,
        'MidStop'     : 2,
        'MdStpPin'    : 'Open',      # Send midstop output signal to Open pin or Counter pin (chinese operator)
        'StopOut'     :  'N.CLS'    # N.CLS = Normally close, N.OPN = Normally open
    }
}

### input pins
inPin = {
    "Open"     : 4,
    "Close"    : 5,
    "Stop"     : 6,
    "OpenLmt"  : 3,
    "CloseLmt" : 2,
    "Up"       : 8,
    "Down"     : 7
    }

outPin = {
    "Open"     : 10,
    "Close"    : 11,
    "Stop"     : 12,
    "Counter"    : 13
    }
   
Input = dict((name, Pin(pin, Pin.IN, Pin.PULL_DOWN)) for (name, pin) in inPin.items())
Output = dict((name, Pin(pin, Pin.OUT)) for (name, pin) in outPin.items())

rotary_sw = Rotary(
    sw_pin = 9,     # select bouton, used to be Prog pin
    clk_pin = 15,    # signal A, used to be Up pin
    dt_pin = 16,      # signal B, used to be Down pin
    half_step = False
    )

Timers = {}
Current = {}
Temp = {}
Parametres = {}


current_sensor = ADC(1)    # read curent at ADC(0)
temp_sensor = ADC(2)      # read temperature at ADC(1)
machine.freq(133000000)   # set cpu frequency

current_timer = Timer()
#temp_timer = Timer()
stopled_timer = Timer()

### some global variables
state = 0
stop_request = False
stop_token_first = False  # used to turn off stop_request signal
is_running = False
in_prog_mode = False
very_first_run = True


def load_file(file):
    """Load json file configuration."""
    global Timers, Current, Temp, Parametres, config
    with open(file, 'r') as infile:
        data = ujson.load(infile)
        config = data
        Timers = data['Timers']
        Current = data['Current']
        Temp = data['Temp']
        Parametres = data['Parametres']
    

def write_file(file):
    """write config to file"""
    with open(file, 'w') as outfile:
        ujson.dump(config, outfile)

### load variables for file
try:
    load_file(filename)
except OSError:
    write_file(filename)
    load_file(filename)

### LCD config
I2C_ADDR     = 0x27
I2C_NUM_ROWS = Parametres['LCD_li']
I2C_NUM_COLS = Parametres['LCD_co']
i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
lcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)

prog_mode_delay = 2                         # delay for press and hold before entre prog mode
delay_readPin = 1        # delay between each iteration to read pin

def initialize():
    """initialization before each run"""
    global state
    global stop_request
    global stop_token_first
    global is_running
    global in_prog_mode
    global menu_current_line, menu_shift, menu_current_level
    
    state = 0
    menu_current_line = menu_shift = menu_current_level = 0
    stop_request = False
    is_running = False
    in_prog_mode = False
    
    for p in Output:
        if p != 'Stop':
            Output[p].value(0)
        
    for p in Input:
        Input[p]        
    ## make sure that open after mid-top is 0 if no mid-stop
    Timers['Opn2'] = 0 if Timers['Mid'] == 0 else Timers['Opn2']
    
    # if wired as normally open, (chinese operator), turn on stop output
    if very_first_run and Parametres['StopOut'] == 'N.OPN':
        Output['Stop'].value(1)
    
    current_timer.deinit()
    #temp_timer.deinit()
    
    lcd.clear()
    lcd.write_line_center("HARMONIE V " + str(version), 1)
    lcd.write_line_center("BIENVENUE", 2)
    utime.sleep(2)
    lcd.clear()
    lcd.write_line_center("Cls:{0:>3},Opn1:{1:>3}".format(Timers['Cls'], Timers['Opn1']), 1)
    lcd.write_line_center("Mid:{0:>3},Opn2:{1:>3}".format(Timers['Mid'], Timers['Opn2']), 2)
    
def readPin(pin, counter = Parametres['btn_lect'] , delay = delay_readPin):
    """Read pin a number of times to determine good signal, delay in msec"""
    read_count = 0
    
    for i in range(counter):
        if Input[pin].value():
            read_count += 1
        utime.sleep_ms(delay)
            
    if read_count == counter:
        return True
    
    return False

def writePin(pin, delay, perm_counter = False, LimitOn = None):
    """Write high value to pin, pause in ms"""
     
    if not stop_request:
        if pin in ['Open', 'Counter'] and Input['OpenLmt'].value() != 1:
            if Parametres['Compteur'] == 'ClsLmt'  and perm_counter == True and LimitOn == 'CloseLmt':
                Output['Counter'].value(1)
            Output[pin].value(1)
            lcd.clear_line(1)
            lcd.clear_line(2)
            lcd.write_line_center("EN OUVERTURE ", 1)
        elif pin == 'Close' and Input['CloseLmt'].value() != 1:
            if Parametres['Compteur'] == 'OpnLmt' and perm_counter == True and LimitOn == 'OpenLmt':
                Output['Counter'].value(1)
            Output[pin].value(1)
            lcd.clear_line(1)
            lcd.clear_line(2)
            lcd.write_line_center("EN FERMETURE ", 1)
        
        utime.sleep_ms(delay)
        Output[pin].value(0)
        Output['Counter'].value(0)
        
    # start reading current
    if Current['Statut'] == 'Active':
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


def stopled_off(timer):
    """Turn off stop led and signal when stop button is declicked."""
    
    global stop_request, stop_token_first, very_first_run
    
    very_first_run = False
    
    if Input['Stop'].value() == 0 and stop_token_first:
        if Parametres['StopOut'] == 'N.OPN':
            Output['Stop'].value(1)
        else:
            Output['Stop'].value(0)


        stop_token_first = False
        stopled_timer.deinit()

def stop_signal_handler(pin):
    """Send stop_request when activate"""
    
    read_count = 0
    global stop_token_first, stop_request
    current_timer.deinit()
    
    stopled_timer.init(freq=10, mode=Timer.PERIODIC, callback=stopled_off)
    
    for i in range(Parametres['btn_lect'] ):
        if Input['Stop'].value():
            read_count += 1
        utime.sleep_ms(delay_readPin)
        
    if (read_count == Parametres['btn_lect'] ) and stop_token_first == False: 
        stop_token_first = True
        stop_request = True
        
        if Parametres['StopOut'] == 'N.OPN':
            Output['Stop'].value(0)
        else:
            Output['Stop'].value(1)

    utime.sleep_ms(Parametres['btn_dura'])

def read_current(timer):
    """Read current in amp"""
    
    global stop_request
    
    counter = 0
    voltage = 0
    
    for _ in range(Current['N_lect']):
        voltage += current_sensor.read_u16()
        utime.sleep_us(10)
    
    voltage = voltage / Current['N_lect']
    
    amp = (voltage * Current['V_max']/65535  - Current['V0_ref']) * (1000/Current['Fcteur'])
    #amp = (max_voltage * Current['V_max']/65535 - 0.0245 - Current['V0_ref']) 
    lcd.write_line_center("I DC: {0:>5.1f} A".format(amp), 3) 

def read_temp():
    """Read temperature"""
     
    voltage = (Temp['V_max']/65535) * temp_sensor.read_u16()
    temp = (voltage - Temp['V0_ref']) * (1000/Temp['Fcteur'])
    lcd.write_line_center('Temp: {0:>5.1f} '.format(temp) + chr(223) + 'C', 4)

def Logic_loop():
    """The main state logic. Core program"""
    global state
    global stop_request
    global is_running
    
    cycle_counter = 0
    
    is_running = True
    
    while not stop_request:
        
        if state == 0:              # initial state
            if readPin('Close'):
                writePin('Close', Parametres['btn_dura'])
                state = 1
            elif readPin('Open'):
                writePin('Open', Parametres['btn_dura'])
                state = 2
        elif state == 1:            # door fully closed, close limit triggers
            if readPin('CloseLmt'):
                current_timer.deinit()
                cycle_counter += 1
                lcd.clear_line(1)
                lcd.clear_line(3)
                lcd.write_line_center("PORTE FERMEE", 1)
                
                if Temp['Statut'] == 'Active':
                    read_temp()    # read and show temperature
                    
                lcd_count_down(Timers['Cls'])
                writePin('Open', Parametres['btn_dura'], perm_counter = True, LimitOn = 'CloseLmt')
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
                writePin('Close', Parametres['btn_dura'], perm_counter = True, LimitOn = 'OpenLmt')
                state = 3 if cycle_counter > 0 and cycle_counter % Parametres['MidStop'] == 0 else 1
        elif state == 3:             # mi-stop
            current_timer.deinit()
            lcd.clear_line(1)
            lcd.clear_line(3)
            lcd.write_line_center("MI-ARRET", 1)
            lcd_count_down(Timers['Mid'])
            
            if Parametres['MdStpPin'] == 'OPEN':
                writePin('Open', Parametres['btn_dura'])
            else:
                writePin('Counter', Parametres['btn_dura'])
            
            state = 4
        elif state == 4:              # door fully opened, after mid-stop
            if readPin('OpenLmt'):
                current_timer.deinit()
                lcd.clear_line(1)
                lcd.clear_line(3)
                lcd.write_line_center("PORTE OUVERTE", 1)
                lcd_count_down(Timers['Opn2'])
                writePin('Close', Parametres['btn_dura'], perm_counter = True, LimitOn ='OpenLmt')
                state = 1
        else:
            print("ERREUR")

def Config_Timers():
    """Configuration for timers open/close and mid-stop"""
    global Timers, config
    is_value_modified = False
    
    menu_key = Menu(sorted(Timers), I2C_NUM_ROWS)
    menu_values = Menu([Timers[k] for k in sorted(Timers)], I2C_NUM_ROWS)
    
    first_time = True
    first_select = True
    while not stop_request:
        sw_value = rotary_sw.value()
        delay_ms = 1
        if first_time:
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.show(), menu_values.show()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<5}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<5}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1

            first_time = False
            
        elif rotary_sw.select():
            ### If the switch is clicked, go into change value mode
            
            value = menu_values.items[menu_key.current_line + menu_key.shift - 1]
            key = menu_key.items[menu_key.current_line + menu_key.shift - 1]
            if not first_select:
                is_value_modified = not is_value_modified
                lcd.write_line('{:<5}:>> {:<8}'.format(key.upper(), value), menu_key.current_line, 1)
            else:
                first_select = False
            
            utime.sleep_ms(300)
            start_time = utime.ticks_ms()
            while is_value_modified and not stop_request:
                sw_value = rotary_sw.value()
                delay_ms = 1
                if sw_value == 1 or readPin('Up'):         # turn clockwise
                    if readPin('Up'): delay_ms = 200
                    value += 1
                    if value > 999: value = 0
                elif sw_value == -1 or readPin('Down'):
                    if readPin('Down'): delay_ms = 200
                    value -= 1
                    if value < 0: value = 999
                elif rotary_sw.select():
                    Timers.update({key: value})
                    config['Timers'] = Timers
                    write_file(filename)
                    load_file(filename)
                    
                    ## update menuitems
                    menu_key.update(sorted(Timers))
                    menu_values.update([Timers[k] for k in sorted(Timers)])
                    is_value_modified = not is_value_modified
                    utime.sleep_ms(300)
                
                elapsed = utime.ticks_diff(utime.ticks_ms(), start_time)
                if elapsed > 200:
                    lcd.write_line('{:<3}'.format(value), menu_key.current_line, 10)
                    start_time = utime.ticks_ms()
                utime.sleep_ms(delay_ms)
                
            lcd.write_line('>> {:<5}: {:<8}'.format(key.upper(), value), menu_key.current_line, 1)                                   
            
        elif sw_value == 1 or readPin('Up'):
            if readPin('Up'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.next(), menu_values.next()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<5}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<5}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        elif sw_value == -1 or readPin('Down'):
            if readPin('Down'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.previous(), menu_values.previous()):
                if is_value_modified:
                    v =- 1
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<5}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<5}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        
        utime.sleep_ms(delay_ms)
    
    # go back to Configuration menu
    Configuration()
        
    
def Config_Current():
    """Configuration for current sensor."""
    global Current, config
    is_value_modified = False
    
    menu_key = Menu(sorted(Current), I2C_NUM_ROWS)
    menu_values = Menu([Current[k] for k in sorted(Current)], I2C_NUM_ROWS)
    
    first_time = True
    first_select = True
    while not stop_request:
        sw_value = rotary_sw.value()
        delay_ms = 10
        if first_time:
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.show(), menu_values.show()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<5}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<5}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
            first_time = False
            
        elif rotary_sw.select():
            ### If the switch is clicked, go into change value mode
            
            value = menu_values.items[menu_key.current_line + menu_key.shift - 1]
            key = menu_key.items[menu_key.current_line + menu_key.shift - 1]
            
            if not first_select:
                is_value_modified = not is_value_modified
                lcd.write_line('{:<6}:>> {:<8}'.format(key.upper(), value), menu_key.current_line, 1)
            else:
                first_select = False

            utime.sleep_ms(250)
            value_format = ''
            start_time = utime.ticks_ms()
            while is_value_modified and not stop_request:
                sw_value = rotary_sw.value()
                delay_ms = 10
                if sw_value == 1 or readPin('Up'):         # turn clockwise\
                    if readPin('Up'): delay_ms = 200
                    if key in ['Statut']:
                        value = 'Active' if value == 'Inactiv' else 'Inactiv'
                        value_format = '{:<8}'
                    elif key in ['N_lect', 'Fcteur']:
                        value += 1
                        value_format = '{:<5}'
                    elif key in ['V_max']:
                        value += 0.1
                        value_format = '{:<5.1f}'
                    elif key in ['V0_ref']:
                        value += 0.001
                        value_format = '{:<6.3f}'

                elif sw_value == -1 or readPin('Down'):
                    if readPin('Down'): delay_ms = 200
                    if key in ['Statut']:
                        value = 'Active' if value == 'Inactiv' else 'Inactiv'
                        value_format = '{:<8}'
                    elif key in ['N_lect', 'Fcteur']:
                        value -= 1
                        if value < 0: value = 0
                        value_format = '{:<5}'
                    elif key in ['V_max']:
                        value -= 0.1
                        if value < 0: value = 0
                        value_format = '{:<5.1f}'
                    elif key in ['V0_ref']:
                        value -= 0.001
                        if value < 0: value = 0
                        value_format = '{:<6.3f}'
                        lcd.write_line('{:<8.3f}'.format(value), menu_key.current_line, 11)
                    
                elif rotary_sw.select():
                    Current.update({key: value})
                    config['Current'] = Current
                    write_file(filename)
                    load_file(filename)
                    
                    ## update menuitems
                    menu_key.update(sorted(Current))
                    menu_values.update([Current[k] for k in sorted(Current)])
                    is_value_modified = not is_value_modified
                    utime.sleep_ms(300)
                
                elapsed = utime.ticks_diff(utime.ticks_ms(), start_time)
                if elapsed > 200:
                    lcd.write_line(value_format.format(value), menu_key.current_line, 11)
                    start_time = utime.ticks_ms()
                utime.sleep_ms(delay_ms)
                    
            lcd.write_line('>> {:<6}: {:<8}'.format(key.upper(), value), menu_key.current_line, 1)                                           
            
        elif sw_value == 1 or readPin('Up'):
            if readPin('Up'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.next(), menu_values.next()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<6}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<6}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        elif sw_value == -1 or readPin('Down'):
            if readPin('Down'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.previous(), menu_values.previous()):
                if is_value_modified:
                    v =- 1
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<6}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<6}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        
        utime.sleep_ms(delay_ms)
    
    # go back to Configuration menu
    Configuration()

def Config_Temp():
    """Configuration for temperature."""
    global Temp, config
    is_value_modified = False
    
    menu_key = Menu(sorted(Temp), I2C_NUM_ROWS)
    menu_values = Menu([ Temp[k] for k in sorted(Temp) ], I2C_NUM_ROWS)
    
    first_time = True
    first_select = True
    
    while not stop_request:
        sw_value = rotary_sw.value()
        delay_ms = 10
        if first_time:
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.show(), menu_values.show()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<5}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<5}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
            first_time = False
            
        elif rotary_sw.select():
            ### If the switch is clicked, go into change value mode
            
            value = menu_values.items[menu_key.current_line + menu_key.shift - 1]
            key = menu_key.items[menu_key.current_line + menu_key.shift - 1]
            
            if not first_select:
                is_value_modified = not is_value_modified
                lcd.write_line('{:<6}:>> {:<8}'.format(key.upper(), value), menu_key.current_line, 1)
            else:
                first_select = False

            utime.sleep_ms(250)
            value_format = ''
            start_time = utime.ticks_ms()
            while is_value_modified and not stop_request:
                sw_value = rotary_sw.value()
                delay_ms = 10
                if sw_value == 1 or readPin('Up'):         # turn clockwise
                    if readPin('Up'): delay_ms = 200
                    if key in ['Statut']:
                        value = 'Active' if value == 'Inactiv' else 'Inactiv'
                        value_format = '{:<8}'
                    elif key in ['Fcteur']:
                        value += 1
                        value_format = '{:<5}'
                    elif key in ['V_max']:
                        value += 0.1
                        value_format = '{:<5.1f}'
                    elif key in ['V0_ref']:
                        value += 0.001
                        value_format = '{:<6.3f}'

                elif sw_value == -1 or readPin('Down'):
                    if readPin('Down'): delay_ms = 200
                    if key in ['Statut']:
                        value = 'Active' if value == 'Inactiv' else 'Inactiv'
                        value_format = '{:<8}'
                    elif key in ['Fcteur']:
                        value -= 1
                        if value <= 0: value = 0
                        value_format = '{:<5}'
                    elif key in ['V_max']:
                        value -= 0.1
                        if value <= 0.1: value = 0
                        value_format = '{:<5.1f}'
                    elif key in ['V0_ref']:
                        value -= 0.001
                        if value <= 0.001: value = 0
                        value_format = '{:<6.3f}'
                    
                elif rotary_sw.select():
                    Temp.update({key: value})
                    config['Temp'] = Temp
                    write_file(filename)
                    load_file(filename)
                    
                    ## update menuitems
                    menu_key.update(sorted(Temp))
                    menu_values.update([Temp[k] for k in sorted(Temp)])
                    is_value_modified = not is_value_modified
                    utime.sleep_ms(300)
                    
                elapsed = utime.ticks_diff(utime.ticks_ms(), start_time)
                if elapsed > 200:
                    lcd.write_line(value_format.format(value), menu_key.current_line, 11)
                    start_time = utime.ticks_ms()
                utime.sleep_ms(delay_ms)
          
            lcd.write_line('>> {:<6}: {:<8}'.format(key.upper(), value), menu_key.current_line, 1)                                           
            
        elif sw_value == 1 or readPin('Up'):
            if readPin('Up'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.next(), menu_values.next()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<6}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<6}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        elif sw_value == -1 or readPin('Down'):
            if readPin('Down'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.previous(), menu_values.previous()):
                if is_value_modified:
                    v =- 1
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<6}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<6}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        
        utime.sleep_ms(delay_ms)
    
    # go back to Configuration menu
    Configuration()

    
def Config_Parametres():
    """"Configuration for LCD"""
    global Parametres, config
    is_value_modified = False
    
    menu_key = Menu(sorted(Parametres), I2C_NUM_ROWS)
    menu_values = Menu([Parametres[k] for k in sorted(Parametres)], I2C_NUM_ROWS)
    
    first_time = True
    first_select = True
    while not stop_request:
        sw_value = rotary_sw.value()
        delay_ms = 1
        if first_time:
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.show(), menu_values.show()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<8}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<8}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
            first_time = False
            
        elif rotary_sw.select():
            ### If the switch is clicked, go into change value mode
            
            value = menu_values.items[menu_key.current_line + menu_key.shift - 1]
            key = menu_key.items[menu_key.current_line + menu_key.shift - 1]
            
            if not first_select:
                is_value_modified = not is_value_modified
                lcd.write_line('{:<8}:>> {:<8}'.format(key.upper(), value), menu_key.current_line, 1)
            else:
                first_select = False
                
            utime.sleep_ms(250)
            value_format = '{:<8}'
            start_time = utime.ticks_ms()
            while is_value_modified and not stop_request:
                sw_value = rotary_sw.value()
                delay_ms = 1
                if sw_value == 1 or readPin('Up'):         # turn clockwise
                    if readPin('Up'): delay_ms = 200
                    if key == 'LCD_li':
                        value = 2 if value == 4 else 4
                    elif key == 'LCD_co':
                        value = 16 if value == 20 else 20
                    elif key == 'StopOut':
                        value = 'N.CLS' if value == 'N.OPN' else 'N.OPN'
                    elif key == 'Compteur':
                        if value == 'OpnLmt':
                            value = 'ClsLmt'
                        elif value == 'ClsLmt':
                            value = 'Inactiv'
                        else:
                            value = 'OpnLmt' 
                    elif key == 'MdStpPin':
                        value = 'OPEN' if value == 'COUNTER' else 'COUNTER'
                    else:
                        value += 1
                        
                elif sw_value == -1 or readPin('Down'):
                    if readPin('Down'): delay_ms = 200
                    if key == 'LCD_li':
                        value = 2 if value == 4 else 4
                    elif key == 'LCD_co':
                        value = 16 if value == 20 else 20
                    elif key == 'StopOut':
                        value = 'N.CLS' if value == 'N.OPN' else 'N.OPN'
                    elif key == 'Compteur':
                        if value == 'OpnLmt':
                            value = 'ClsLmt'
                        elif value == 'ClsLmt':
                            value = 'Inactiv'
                        else:
                            value = 'OpnLmt'         
                    elif key == 'MdStpPin':
                        value = 'OPEN' if value == 'COUNTER' else 'COUNTER'
                    else:
                        value -= 1
                        if value <= 1: value = 1
                        
                elif rotary_sw.select():
                    Parametres.update({key: value})
                    config['Parametres'] = Parametres
                    write_file(filename)
                    load_file(filename)
                    
                    ## update menuitems
                    menu_key.update(sorted(Parametres))
                    menu_values.update([ Parametres[k] for k in sorted(Parametres) ])
                    is_value_modified = not is_value_modified
                    utime.sleep_ms(300)
                
                elapsed = utime.ticks_diff(utime.ticks_ms(), start_time)
                if elapsed > 200:
                    lcd.write_line(value_format.format(value), menu_key.current_line, 13)
                    start_time = utime.ticks_ms()
                utime.sleep_ms(delay_ms)
                
            lcd.write_line('>> {:<8}: {:<8}'.format(key.upper(), value), menu_key.current_line, 1)                                   
            
        elif sw_value == 1 or readPin('Up'):
            if readPin('Up'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.next(), menu_values.next()):
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<8}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<8}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        elif sw_value == -1 or readPin('Down'):
            if readPin('Down'): delay_ms = 200
            lcd.clear()
            line = 1
            for k, v in zip(menu_key.previous(), menu_values.previous()):
                if is_value_modified:
                    v =- 1
                if line == menu_key.current_line:
                    lcd.write_line('>> {:<8}: {:<8}'.format(k.upper(), v), line, 1)
                else:
                    lcd.write_line('{:<8}: {:<8}'.format(k.upper(), v), line, 3)
                line += 1
        
        utime.sleep_ms(delay_ms)
    
    # go back to Configuration menu
    Configuration()
    
    
### menu
menu = Menu(["Minuterie", "Courant", "Temperature", "Parametres"], I2C_NUM_ROWS)
menu_fct = [Config_Timers, Config_Current, Config_Temp, Config_Parametres]


def Configuration():
    """Configuration main menu."""
    global in_prog_mode, stop_request
    
    stop_request = False
    first_time = True
    
    while not stop_request:
        sw_value = rotary_sw.value()
        delay_ms = 1
        if first_time:
            line = 1
            lcd.clear()
            for item in menu.show():
                if line == menu.current_line:
                    lcd.write_line('>> ' + item.upper(), line, 1)
                else:
                    lcd.write_line(item.upper(), line, 5)
                line += 1
            first_time = False
            utime.sleep_ms(500)
            
        elif sw_value == 1 or readPin('Up'):    # turn clockwise
            delay_ms = 1 if sw_value == 1 else 200
            line = 1
            lcd.clear()
            for item in menu.next():
                if line == menu.current_line:
                    lcd.write_line('>> ' + item.upper(), line, 1)
                else:
                    lcd.write_line(item.upper(), line, 5)
                line += 1
        elif sw_value == -1 or readPin('Down'):    # turn counter-clockwise
            delay_ms = 1 if sw_value == 1 else 200
            line = 1
            lcd.clear()
            for item in menu.previous():
                if line == menu.current_line:
                    lcd.write_line('>> ' + item.upper(), line, 1)
                else:
                    lcd.write_line(item.upper(), line, 5)
                line += 1
                
        elif rotary_sw.select():
            menu_fct[menu.current_line + menu.shift - 1]()
            
        utime.sleep_ms(delay_ms)

        
def main():
    """Main program, call others functions"""
    #global state
    global stop_request
    global is_running
    global in_prog_mode
    
    initialize()
    
    #_thread.start_new_thread(stop_signal_handler, ())
    
    while True:
        if not is_running:
            if (readPin('Close') or readPin('Open')) and not stop_token_first:
                Logic_loop()
            elif rotary_sw.select() and not stop_token_first:
                Configuration()
        if stop_request:
            initialize()
        
        utime.sleep_ms(10)            

# listen to Stop interrupt
Input['Stop'].irq(trigger=Pin.IRQ_RISING, handler=stop_signal_handler)


if __name__ == '__main__':
    main()