import machine as m
import utime
import _thread


led_red = m.Pin(16, m.Pin.OUT)
button = m.Pin(20, m.Pin.IN)

stop_request = False

def button_handler(pin):
    button.irq(handler=None)
    global stop_request
    stop_request = True

button.irq(trigger=m.Pin.IRQ_RISING, handler=button_handler)

while not stop_request:
    led_red.toggle()
    utime.sleep_ms(500)

print("OFF")
led_red.value(0)
