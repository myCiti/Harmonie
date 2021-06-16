from machine import Pin
import utime

button_pin = Pin(9, Pin.IN, Pin.PULL_DOWN)
direction_pin = Pin(8, Pin.IN, Pin.PULL_DOWN)
step_pin  = Pin(7, Pin.IN, Pin.PULL_DOWN)

previous_value = False
button_down = False
counter = 0

while True:
    if previous_value != step_pin.value():
        if step_pin.value() == False:
            if direction_pin.value() == False:
                print("{0:>4}: Sens horaire".format(counter))
            else:
                print("{0:>4}: Sens anti-horaire".format(counter))
        
        previous_value = step_pin.value()
        counter += 1
    
    utime.sleep_ms(1)
    