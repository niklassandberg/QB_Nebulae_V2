import leddriver
import time
import sys
import random
import colorsys

def blendColor(color_a, color_b, amount):
    newred = (color_a.red() * (1.0 - amount)) + (color_b.red() * amount)
    newgreen = (color_a.green() * (1.0 - amount)) + (color_b.green() * amount)
    newblue = (color_a.blue() * (1.0 - amount)) + (color_b.blue() * amount)
    return leddriver.Color(newred, newgreen, newblue) # defaults to white.

ledDriver = leddriver.LedDriver()
pink = leddriver.Color(3037, 200, 3825)
white = leddriver.Color(4095,4095,4095)
red = leddriver.Color(4095, 0, 0)
orange = leddriver.Color(4095, 1100, 0) 
yellow = leddriver.Color(4095, 3395, 0)
blue = leddriver.Color(0,0,4095) 
green = leddriver.Color(0, 4095, 0) 
purple = leddriver.Color(511, 0, 4095) 

if len(sys.argv) > 1:
    arg = sys.argv[1]
    if arg == "booting":
        tempc = white
    elif arg == "loading":
        tempc = blue
    elif arg == "loadingusb":
        tempc = blendColor(blue, green, 0.5)
    elif arg == "updating":
        tempc = green
    elif arg == "error":
        tempc = red
    elif arg == "calibration":
        tempc = yellow
    elif arg == "wifi":
        tempc = purple
    else:
        print "Unknown LED option"
        tempc = leddriver.Color(r=4095, g=0, b=1024)
    if len(sys.argv) > 2 and sys.argv[2] == "pulse":
        behavior = "pulse"
    elif len(sys.argv) > 2 and sys.argv[2] == "rainbow":
        behavior = "rainbow"
    else:
        behavior = "cycle"
else:
    tempc = leddriver.Color()
    print "No argument present, defaulting to white"
    print "use any of the following arguments:"
    print "booting (default)"
    print "loading"
    print "updating"
    print "error"
    print "calibration"
    print "You can add a second argument to control if the LEDs will cycle or pulse:"
    print "pulse"
    print "cycle (default)"
    print "Example"
    print "sudo python2 nebulae/bootleds.py loading pulse"
    

#try:
while True:
    now = int(round(time.time() * 1000.0))
    bright = [0, 0, 0, 0, 0]
    for i in range(0, 5):
        dur = 1000.0
        temptime = now + (i * (dur / 5))
        if behavior == "cycle":
            bright[i] = abs(((temptime % dur) / (dur / 2)) - 1.0)
        elif behavior == "rand":
            #b = int(float(tempc.blue()) * random.uniform(0.9, 1.1)) % 4096
            #g = int(float(tempc.green()) * random.uniform(0.9, 1.1)) % 4096
            #r = int(float(tempc.red()) * random.uniform(0.9, 1.1)) % 4096
            blue = tempc.blue()+int(temptime*10)
            green = tempc.green()+int(temptime*(-40))
            red = tempc.red()+int(temptime*30)

            if(blue<0) :
                blue = 4096 + blue
            elif(blue>4096) :
                blue = blue - 4096
            
            if(green<0) :
                green = 4096 + green
            elif(green>4096) :
                green = green - 4096

            if(red<0) :
                red = 4096 + red
            elif(blue>4096) :
                red = red - 4096

            #tempc.r = red
            #tempc.g = green
            #tempc.b = blue
            tempc = leddriver.Color(red, green, blue)

            bright[i] = abs(((temptime % dur) / (dur / 2)) - 1.0)
        elif behavior == "rainbow":
            hue = (time.time() * 0.3) % 1.0
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            r = int(rgb[0] * 4095)
            g = int(rgb[1] * 4095)
            b = int(rgb[2] * 4095)
            tempc = leddriver.Color(r, g, b)
            bright[i] = abs(((temptime % dur) / (dur / 2)) - 1.0)
        else:
            bright[i] = (abs(((now & 400) - 200.0)) / 400.0)  # this is not right and still ugly.
    ledDriver.update()
    ledDriver.set_rgb("speed_neg", tempc.red(), tempc.green(),tempc.blue(), bright[4])
    ledDriver.set_rgb("speed_pos", tempc.red(), tempc.green(),tempc.blue(), bright[3])
    ledDriver.set_rgb("pitch_neg", tempc.red(), tempc.green(), tempc.blue(), bright[2])
    ledDriver.set_rgb("pitch_pos", tempc.red(), tempc.green(), tempc.blue(), bright[1])
    ledDriver.set_button_led("record", bright[0])
    ledDriver.set_button_led("next",  bright[1])
    ledDriver.set_button_led("source", bright[2])
    ledDriver.set_button_led("reset", bright[3])
    ledDriver.set_button_led("freeze", bright[4])

#except (KeyboardInterrupt, SystemExit):
#    print "Keyboard Interrupt or System Exit"
#    raise
#except:
#    print "Error"
