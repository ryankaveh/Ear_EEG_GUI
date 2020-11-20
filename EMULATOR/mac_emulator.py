import os, subprocess, serial, struct, time, threading
import numpy as np
from multiprocessing import Process, Queue


# This currently works! We can change the names of the emulated ports but it doesn't really matter.
# It's currently set up to be independant of anything else. You just need to run this python script
# and it will open up dummy serial ports, ttyChip and ttyGUI.
#
# ttyChip is meant to be the Ear EEG chip side of the serial link while ttyGui is the GUI side of the emulator.
# If you'd like to communicate through this emulated serial link, you need to open up ttyGui using pyserial like so:
# 
#   client_port='./ttyGUI'
#   serialGUISide = serial.Serial(client_port, 9600, rtscts=True, dsrdtr=True)
# 
# Ideally everything should just work from there. You run this and then in a separate thread/process/terminal you will
# run your own program that opens up a serial port with pyserial and you can communicate with the emulated Ear EEG Chip 

# If you're on a mac/linux machine you can open a terminal and see what's coming out of a serial port with:
#   cat < ./ttyGUI
# 
# and you can send stuff through the serial port with (not you need to send it through the opposite end):
#   echo "test" > ./ttydevice

class serial_emulator(object):
    def __init__(self, device_port='./ttyChip', client_port='./ttyGUI'):
        self.device_port = device_port
        self.client_port = client_port
        cmd=['/usr/local/Cellar/socat/1.7.3.4/bin/socat','-d','-d','PTY,link=%s,raw,echo=0' %
                self.device_port, 'PTY,link=%s,raw,echo=0' % self.client_port]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1)
        self.serialChipSide = serial.Serial(self.device_port, 9600, rtscts=True, dsrdtr=True)
        self.err = ''
        self.out = ''

    def write(self, out):
        print(out)
        self.serialChipSide.write(out)

    def read(self):
        line = ''
        while self.serialChipSide.inWaiting() > 0:
            line += (self.serialChipSide.read()).decode('utf-8')
        return line

    def __del__(self):
        self.stop()

    def stop(self):
        self.proc.kill()
        self.out, self.err = self.proc.communicate()


def earEEG_genDummyData(index, yData):
    xVal = index * .01
    yVal = yData[index%len(yData)]
    # print(index)
    # print(index%len(yData))
    tup = (xVal, yVal)
    return struct.pack("dd", *tup)

def earEEG_process(messageQueue, responseQueue):

    print("\nNew thread started!")

    # Make earEEG I/O emulator
    # Can write bytes with serial_emulator.write(string.encode('utf-8'))
    # Can read bytes from it with serial_emulator.read()
    earEEG = serial_emulator('./ttyChip','./ttyGUI')

    # set various flag & starting datapoint
    start_flag = 0
    index = 0
    npX = np.arange(0, 1, 0.01)
    yData = list(np.sin(4 * np.pi * npX))


    while True:
        # time delay (1 mS)
        time.sleep(.1)
        # time.sleep(2) 
        
        # Use this if statement to start and stop
        # the dummy data generation from the terminal you used to
        # start this script
        if (messageQueue.empty() == False):
            msg = messageQueue.get()

            if (msg == 'start'):
                print("starting earEEG dummy data generator")
                start_flag = 1
            
            if (msg == 'stop'):
                print("heard stop - will stop now")
                break
        
        ## Use this if statement to start and stop data generation through the serial link (this is best)
        # if (start_flag == 0):
        # line = earEEG.read()
        #     if (line == 'start'):
        #         print("starting earEEG dummy data generator")
        #         start_flag = 1
            
        #     if (line == 'stop'):
        #         print("heard stop - will stop now")
        #         break

        if (start_flag == 1):
            # generate & write data to COM Port
            out = earEEG_genDummyData(index, yData)
            earEEG.write(out)
            index += 1
            print(index)
            # line = earEEG.read()
            # responseQueue.put(line)


    
    print("earEEG_process finished")

if __name__ == '__main__':

    # First we need to make the machinery
    # some queues and a multiprocesser object

    # queue from host side to earEEG_emulator
    # for star & stopping!
    messageQueue = Queue() 

    # queue from earEEG_emulator to host
    responseQueue = Queue()

    earEEG_process = threading.Thread(target=earEEG_process, args=(messageQueue,responseQueue,))
    print("about to start thread")
    earEEG_process.start()
    # to start data dumping process
    print("Waiting for user to start data generation...")
    flag_running = 1
    while (flag_running == 1):
        cmd = input(" options: start to start, stop to stop\n")
        messageQueue.put(cmd)
        if (cmd == "stop"):
            break

    print("stopping... emptying data buffer")
    while (responseQueue.empty() == False):
        msg = responseQueue.get()
        print(msg)
    #
    #

    # to stop data dumping
    print("stopping...")
    messageQueue.put("stop")
    earEEG_process.join()
