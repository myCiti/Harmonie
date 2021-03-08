import machine
import utime

sda=machine.Pin(0)
scl=machine.Pin(1)
i2c=machine.I2C(0,sda=sda, scl=scl, freq=400000)
i2c.writeto(39, '\x01')
i2c.writeto(39, '\x04')
i2c.writeto(39, "MMMMMMMM")
utime.sleep(1)