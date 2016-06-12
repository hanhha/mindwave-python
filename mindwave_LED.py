import mindwave, time
import RPi.GPIO as GPIO

# initialise PWM pin
GPIO.setmode(GPIO.BOARD)  # BOARD numbering

LED = 11  # BOARD Pin 11 == BCM Pin 17
GPIO.setup(LED, GPIO.OUT)

pwm_LED = GPIO.PWM(LED, 100)
pwm_LED.start(0)

# setup headset
headset = mindwave.Headset('/dev/ttyUSB0', '1E5F')
time.sleep(2)

headset.connect()
print "Connecting..."

while headset.status != 'connected':
    time.sleep(0.5)
    if headset.status == 'standby':
        headset.connect()
        print "Retrying connect..."
print "Connected."

while True:
    time.sleep(.5)
    print "Attention: %s, Meditation: %s" % (headset.attention, headset.meditation)
    if headset.attention > 30:
        pwm_LED.ChangeDutyCycle(min(100, headset.attention-30))
    else:        
        pwm_LED.ChangeDutyCycle(0)





