import os, serial
from time import sleep, time
from csv import writer
from ctypes import Structure, c_ubyte, c_short, c_int
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QCheckBox, QLineEdit
from PyQt5.QtCore import QTimer

# The SerialReader class handles sending/receiving data to/from the usb dongle over pyserial
class SerialReader():

    def __init__(self, port, numChannels, channelDataArr, saveDataQueue, connectionPipe, commandWriterPipe, commandResponsePipe):

        self.serialGUISide = None
        self.port = port
        self.numChannels = numChannels
        self.channelDataArr = channelDataArr
        self.saveDataQueue = saveDataQueue
        self.connectionPipe = connectionPipe
        self.commandWriterPipe = commandWriterPipe
        self.commandResponsePipe = commandResponsePipe

        self.refreshRate = 10 # Refresh rate in ms, only used when in command mode
        self.commandMode = True # Controls whether serialReader is looking for data or command responses, always starts in command mode

    # Waits for serial port connection and, once established, starts a loop to read data from and write commands to the pyserial connection
    def startSerialReader(self):

        while not self.serialGUISide: # This waits for a device at the given port to be connected
            sleep(0.1) # This caps the refresh rate and lowers the load on the computer, full speed not needed
            try:
                # Connection is in startSerialReader in order to work with multiprocessing
                # self.serialGUISide = serial.Serial(self.port, 9600, rtscts=True, dsrdtr=True) # Uncomment for emulator
                self.serialGUISide = serial.Serial(self.port, 115200, rtscts=True) # Creates connection with specified port, baud doesn't actually matter
            except:
                pass

        self.connectionPipe.send(1) # Callback to notify main loop that device is connected
        print("Writing stop to chip")
        # Stop is written to stop any data already streaming (in case of a malfunction), written three times as the first command sometimes doesn't get through
        self.serialGUISide.write(("stop" + " \n").encode())
        self.serialGUISide.write(("stop" + " \n").encode())
        self.serialGUISide.write(("stop" + " \n").encode())

        while True:
            self.updateData() # Data read in happens here
            if self.commandWriterPipe.poll(): # Checks if there is a command to write to the chip
                command = self.commandWriterPipe.recv().strip() # Gets command and removes any extra whitespace 
                print("Writing " + command + " to chip")
                self.serialGUISide.write((command + " \n").encode()) # Space has to be added for chip parsing
                if command == "start":
                    self.commandMode = False # Data read will now expect eeg data to be streaming
                elif command == "stop":
                    self.commandMode = True # Data read will only expect responses to commands
                    # Waits for eeg data to finish arriving and throws it away, old usage, should be included if pyserial reset is removed
                    # sleep(0.5) 
                    # self.serialGUISide.reset_input_buffer()
                    self.resetPyserial() # Issues appear on stop, pyserial reset fixes them
                elif command == "pyserialReset": 
                   self.resetPyserial()

    # Works to reset the pyserial connection with the USB, fixes many connection issues
    def resetPyserial(self):

        # Closes and recreates connection and then throws away any remaining data in buffers
        self.serialGUISide.close()
        self.serialGUISide = serial.Serial(self.port, 115200, rtscts=True)
        self.serialGUISide.reset_output_buffer()
        self.serialGUISide.reset_input_buffer()

        # Checks new connections is successful by writing 'single' command and looking for response
        self.serialGUISide.write(("single \n").encode()) 
        print("Connection reset, writing single to chip and looking for response")
        sleep(0.1)

        if self.serialGUISide.in_waiting == 0: # If no response is found it tries resetting the connection again
            print("No response, resetting again")
            self.serialGUISide.close()
            self.serialGUISide = serial.Serial(self.port, 115200, rtscts=True)
            self.serialGUISide.reset_output_buffer()
            self.serialGUISide.reset_input_buffer()
            self.serialGUISide.write(("single \n").encode())
            print("Connection reset, writing single to chip and looking for response")
            sleep(0.1)

            if self.serialGUISide.in_waiting == 0: # Gives up after two attempts, can retry by clicking button again
                print("No response, connection reestablishment failure")

        if self.serialGUISide.in_waiting > 0: # If a response is found, the reset has succeeded and the response is thrown away
            print("Response obtained, connection reestablishment success")
            self.serialGUISide.reset_input_buffer()

    # Handles all data reading from the pyserial port, saves eeg data so it can be accessed by the rest of the GUI
    def updateData(self):

        if self.commandMode: # Indicates GUI is not expecting eeg data to be streaming, just command responses
            sleep(self.refreshRate * 0.001) # This caps the refresh rate and lowers the load on the computer, full speed not needed
            if self.serialGUISide.in_waiting > 0: # If data exists to be read
                sleep(0.1) # Make sure full response is transmitted
                val = b''
                val += self.serialGUISide.read(self.serialGUISide.in_waiting) # Reads all data from the USB dongle
                # Currently reponses are handled in hex as that is how the chip sends them, text responses can be decoded with code below
                print("Chip response: " + str(val.hex()))
                self.commandResponsePipe.send("Chip: " + str(val.hex()))
                # print("Chip response: " + val.decode())
                # self.commandResponsePipe.send("Chip: " + val.decode())
                

        elif self.serialGUISide.in_waiting > 0: # If data exists to be read
            if self.serialGUISide.in_waiting < 6: #TODO
                self.serialGUISide.reset_input_buffer()

            val = b''
            val += self.serialGUISide.read(65) # Reads one packet of eeg data which is always exactly 65 bytes long

            packetId = int.from_bytes(val[:1], "big") # Extracts packet id from first byte
            
            saveData = [packetId]

            idx = 0
            for i in range(1, len(val) - 1, self.numChannels):
                # Decodes one channel (eight bytes) at a time from the packet
                chxEEG = int.from_bytes(val[i:i+4], "big", signed=True)
                chxI = int.from_bytes(val[i+4:i+6], "big", signed=True)
                chxQ = int.from_bytes(val[i+6:i+8], "big", signed=True)

                # Fills the channels multiprocessing array with the new data
                with self.channelDataArr[idx].get_lock():
                    self.channelDataArr[idx].packetId = packetId
                    self.channelDataArr[idx].chxEEG = chxEEG
                    self.channelDataArr[idx].chxI = chxI
                    self.channelDataArr[idx].chxQ = chxQ
                idx += 1

                saveData.extend((chxEEG, chxI, chxQ)) # Data is added here to be saved later
            
            self.saveDataQueue.put(saveData) # The full packet of data is sent to be saved by the SaveDataWriter

# Class allows for construction of the multiprocessing array to share channel data
class ChannelData(Structure):
    _fields_ = [("packetId", c_ubyte), ("chxEEG", c_int), ("chxI", c_short), ("chxQ", c_short)]

# Button to pull up the data saving options
class SaveDataMenuButton(QPushButton):

    def __init__(self, running):

        super().__init__("Save Data") # Creates button that says 'Save Data'
        self.clicked.connect(self.showPopup) # Calls the showPopup function on click

        self.running = running

        # Creates window that serves as the save data menu, menu is intially hidden
        self.menu = SaveDataMenu(self, self.running)

    # Called on button click, displays menu
    def showPopup(self):

        self.menu.show()

class SaveDataMenu(QWidget):

    def __init__(self, button, running):

        super().__init__()
        layout = QVBoxLayout()

        self.updatedFilename = False
        self.button = button

        self.saveState = QCheckBox("Save Data")
        self.saveState.setCheckState(2) # 0 is unchecked, 2 is checked, default is to save data
        self.saveState.setEnabled(not running.value)

        self.filename = str(time()) # Default filename is the current time
        self.filenameLable = QLabel("Filename:")
        self.filenameBox = QLineEdit(self.filename)
        self.filenameBox.textChanged.connect(self.filenameChanged)
        self.filenameBox.setEnabled(not running.value)

        self.filenameLayout = QHBoxLayout()
        self.filenameLayout.addWidget(self.filenameLable)
        self.filenameLayout.addWidget(self.filenameBox)

        self.tooltip = QLabel("Please enter your desired filename\nOn each start and stop numbers will be added to the end\n(abc -> \"abc-0\")")

        layout.addWidget(self.saveState)
        layout.addLayout(self.filenameLayout)
        layout.addWidget(self.tooltip)

        self.setLayout(layout)

    def setChangeable(self, changeable):

        self.saveState.setEnabled(changeable)
        self.filenameBox.setEnabled(changeable)

    def filenameChanged(self, currText):

        self.filename = str(currText)
        self.updatedFilename = True

class SaveDataWriter(QWidget):

    def __init__(self, running, numChannels, saveDataQueue, saveDataMenuButton):

        super().__init__()

        # Header format: ["packet_id", "chx1_eeg", "chx1_i", "chx1_q", "chx2_eeg", "chx2_i", "chx2_q", ...]
        self.header = ["packet_id"] + [itm for lst in [[chxNum + "_eeg", chxNum + "_i", chxNum + "_q"] for chxNum in ["chx" + str(i) for i in range(numChannels)]] for itm in lst]

        self.running = running
        self.saveDataQueue = saveDataQueue
        self.saveDataMenuButton = saveDataMenuButton

        self.setCurrFilename()

        self.refreshRate = 5 # Refresh rate in ms, controls how often new data is looked for

        self.hide()

    def startSaveDataWriter(self):

        self.timer = QTimer()
        self.timer.setInterval(self.refreshRate)
        self.timer.timeout.connect(self.writeData)
        self.timer.start()

    def writeData(self):

        if bool(self.saveDataMenuButton.menu.saveState) and bool(self.running.value) and not self.saveDataQueue.empty():
            saveData = self.saveDataQueue.get() # Possibly not exitable on windows? https://docs.python.org/3/library/queue.html#put
            shouldWriteHeader = not os.path.exists(self.currFilename)

            with open(self.currFilename, 'a') as csvfile:
                dataWriter = writer(csvfile) # CSV writer
                if shouldWriteHeader:
                    dataWriter.writerow(self.header)
                dataWriter.writerow(saveData)
            self.updatedExtenstion = False

        elif (not self.updatedExtenstion or self.saveDataMenuButton.menu.updatedFilename) and not bool(self.running.value):
            self.setCurrFilename()

        # This clause works to empty the queue if the user hasn't yet clicked start
        elif not bool(self.running.value) and not self.saveDataQueue.empty():
            self.saveDataQueue.get()

    def setCurrFilename(self):

        idx = 0
        self.currFilename = "../data/" + str(self.saveDataMenuButton.menu.filename) + "-" + str(idx) + ".csv"
        while os.path.exists(self.currFilename):
            idx += 1
            self.currFilename = "../data/" + str(self.saveDataMenuButton.menu.filename) + "-" + str(idx) + ".csv"
        self.updatedExtenstion = True
        self.saveDataMenuButton.menu.updatedFilename = False
        