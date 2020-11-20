import os, subprocess, serial, time
import threading
from multiprocessing import Process, Queue


#
#
data_counter = 0
packet_id = 0

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


def earEEG_genDummyData():
    global data_counter
    global packet_id
    # eeg_data_chXX = {eeg_out[63:40],impedance_out_i[39:24],impedance_out_q[23:8], edo_out[7:0]};
    # EEG_NEURAL_DATA_WIDTH = 24;
    # EEG_IMPEDANCE_DATA_WIDTH = 16;
    # EEG_EDO_DATA_WIDTH = 8;
    #
    # eeg_packet <= {eeg_packet_msb,eeg_packet_id[6:0],
    #               eeg_data_channel_7,eeg_data_channel_6,eeg_data_channel_5,
    #               eeg_data_channel_4,eeg_data_channel_3,eeg_data_channel_2,
    #               eeg_data_channel_1,eeg_data_channel_0};

    chx_EEG = (data_counter + 1).to_bytes(3,'big')
    chx_EDO = (data_counter + 2).to_bytes(1,'big')
    chx_i   = (data_counter + 3).to_bytes(2,'big')
    chx_q   = (data_counter + 3).to_bytes(2,'big')

    pkt_id = (packet_id).to_bytes(1,'big')


    chx = chx_EEG + chx_i + chx_q + chx_EDO

    for i in range(0,7):
        chx += chx
    
    packet = pkt_id + chx

    if (packet_id < 254):
        packet_id = packet_id + 1
    else:
        packet_id = 0

    if (data_counter < 253):
        data_counter = data_counter + 2
    else:
        data_counter = 0

    # print(newData)
    return (packet)

def earEEG_process(messageQueue, responseQueue):

    print("\nNew thread started!")

    # Make earEEG I/O emulator
    # Can write bytes with serial_emulator.write(string.encode('utf-8'))
    # Can read bytes from it with serial_emulator.read()
    earEEG = serial_emulator('./ttyChip','./ttyGUI')

    # set various flag & starting datapoint
    start_flag = 0
    lastData = 0

    while True:
        # time delay (1 mS)
        time.sleep(.001)
        #time.sleep(2) 
        
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
            data = earEEG_genDummyData()
            lastData = data
            earEEG.write(data)
            line = earEEG.read()
            responseQueue.put(line)


    
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
