import machine
import utime
import ujson

filename = 'config.json'

config = {
    'Opn1' : 50,
    'Opn2' : 5,
    'Cls'  : 5,
    'Mid'  : 5
    }

try:
    with open(filename) as fp:
        data = ujson.load(fp)
        for p in data:
             config[p] = data[p]
except OSError:
    with open(filename, 'w') as file:
        ujson.dump(config, file)