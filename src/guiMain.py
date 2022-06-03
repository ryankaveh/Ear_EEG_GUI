import os, sys, argparse
from time import sleep
from csv import reader, writer
from serial.tools import list_ports
import multiprocessing as mp
from PyQt5.QtWidgets import QApplication, QMainWindow, QGridLayout, QVBoxLayout, QHBoxLayout, QWidget, QComboBox

import guiCue
import guiData
import guiOptions
import guiPlots

###
# Known Issues:
#
# AttributeError: 'ForkAwareLocal' object has no attribute 'connection' appears to be something with the sync manager shutting down? Or maybe too many simultaneous manager reads? 
# A rare error but problematic. 
# Maybe something to do when packet ids are the same, error creating same packet id triggers this on some processes (not all) every time
# 
# Clean Code
#   TODOS
#   Comments + documentation
# Testing
# Split mac/windows
###
class MainWindow(QMainWindow):

    def __init__(self, commandLinePort):

        super().__init__()

        self.setWindowTitle("Ear EEG GUI")

        numChannels = 8 # Number of channels to expect, will definitely break if value is incorrect
        vid = 0x1915 # Nordic device vendor id, used for auto connect, change if desired connectionb device changes
        pid = 0x521A # Corrosponding product id, use same as vendor id
        configFilename = "guiConfig.csv" # Filename from which to save and load plot configurations, regenerated automatically on deletion
        startupCommandsFilename = "startupCommands.txt" # Filename from which to run commands automatically on connection, step skipped if file not found
        regDumpFilename = "regDump.txt" # Filename in which to append dumped registers

        # List of all DataProcesses backends that be shown as graphs
        # Contains ("Graph Name", DataProcess) tuples
        plotDataProcesses = []

        running = mp.Value('i', False) # Controls whether the DataProcesses update and CustomGraphWidgets redraw themselves across all processes

        # Sets port to read data from to command line input if entered
        if commandLinePort:
            port = commandLinePort
        # If no command line argument, port is found automatically based on device and vendor info
        else:
            # port = "../EMULATOR/ttyGUI" # Hardcoded port formulator, if so comment out following block
            # port = "/dev/cu.usbmodem0000000000001" Used to manually set port, if so comment out following block
            set = False
            for device in list_ports.comports():
                if device.vid == vid and device.pid == pid:
                    port = device.device
                    print("Correct port found to be " + port + ", connecting...")
                    set = True
            # If no port with the correct vendor and device id is found, it falls back to a preset port
            if not set:
                port = "/dev/cu.usbmodem0000000000001"
                print("Auto connection failed, no device with correct vendor and product id found, reverting to default: " + port)
        
        # List of numChannels (currently 8) C structs that hold the current packet id and channel data for each channel
        # Used by DataProcesses to generate the graph data for all graphs
        # Initalized to 0s, lock used to keep all data and corresponding packet id synchronized
        channelDataArr = []
        for i in range(0, numChannels):
            lock = mp.RLock()
            channelDataArr.append(mp.Value(guiData.ChannelData, 0, 0, 0, 0, lock=lock))

        self.manager1 = mp.Manager() # Manager used to spawn all multiprocessing processes and generate multiprocessing objects
        self.manager2 = mp.Manager() # Managers have an internal limit on how many objects they can generate simultaneously, multiple need to avoid occasional crashes
        self.manager3 = mp.Manager()
        saveDataQueue = self.manager1.Queue() # This queue is used to send data from the SerialReader to the SaveDataWriter

        connectionPipe, sRConnectionPipe = mp.Pipe() # Sends a 1 to let main processes know that the device is successfully connected
        commandWriterPipe, sRCommandWriterPipe = mp.Pipe() # Used to send commands from the chat window (main process) to the SerialReader (handles chip interactions)
        commandResponsePipe, sRCommandResponsePipe = mp.Pipe() # Used to send the chip response from commands from SerialReader to the chat window

        # Creates SerialReader object to read data from serial port "port", populate channelDataArr, and save the data to saveDataQueue
        # The SerialReader update function runs on a different process and handles all interactions with the chip (data and commands)
        serialReader = guiData.SerialReader(port, numChannels, channelDataArr, saveDataQueue, sRConnectionPipe, sRCommandWriterPipe, commandResponsePipe)
        self.serialReaderProcess = mp.Process(target=serialReader.startSerialReader)
        self.serialReaderProcess.daemon = True
        self.serialReaderProcess.start()

        xAxisLength = 100 # Default length of the xAxis, repersents number of packets so depending on what % of packets of graphed, corresponding time changes

        self.processes = [] # Contains all post-processing processes (which then send data to their corresponding graph)
        for i in range(numChannels): # Each channel has three different post-processes applied
            managedX = self.manager1.list() # List of the most recent X values, updated by data process then used by the graph
            managedY = self.manager1.list() # List of the most recent X values, updated by data process then used by the graph
            managedAxisLen = mp.Value('i', xAxisLength) # Shared xAxis length between main process (updates this value) and data process (uses this value)
            eegDataProcess = guiPlots.EEGDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen)
            p = mp.Process(target=eegDataProcess.startUpdateData) # Starts the while loop that will check for new data
            p.daemon = True # Forces processes to end when program is closed 
            p.start()
            self.processes.append(p)

            plotDataProcesses.append(("Ch " + str(i) + " EEG", eegDataProcess)) # Adds name and data process to the possible graphs

            managedX = self.manager2.list()
            managedY = self.manager2.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            iQMagDataProcess = guiPlots.IQMagDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen)
            p = mp.Process(target=iQMagDataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            plotDataProcesses.append(("Ch " + str(i) + " mag(I&Q)", iQMagDataProcess))

            managedX = self.manager3.list()
            managedY = self.manager3.list()
            managedAxisLen = mp.Value('i', xAxisLength)
            iQPhaseDataProcess = guiPlots.IQPhaseDataProcess(running, channelDataArr[i % numChannels], managedX, managedY, managedAxisLen)
            p = mp.Process(target=iQPhaseDataProcess.startUpdateData)
            p.daemon = True
            p.start()
            self.processes.append(p)

            plotDataProcesses.append(("Ch " + str(i) + " phase(I&Q)", iQPhaseDataProcess))

        plotLayout = [] # 2d array containing arrays representing each column, inside inner arrays are the numbers corresponding with which graph to show
        if os.path.exists(configFilename): # If a config file exists this block will load it and arrange the plots accordingly
            print("Loading Config")
            with open(configFilename, 'r') as config:
                configReader = reader(config) # CSV reader
                for plotCol in configReader:
                    plotLayout.append([int(plotNum) for plotNum in plotCol]) # Converts to ints from strings and adds the row to the layout

        if (not os.path.exists(configFilename)) or (not len(plotLayout) == 2): # There are two columns, this needs to be changed if the number of columns changes
            print("Config Missing or Broken, Regenerating")
            plotLayout = [[0,1],[2,3]] # Default plot layout shows these four plots in a 2x2
            with open(configFilename, 'w') as config:
                configWriter = writer(config) # CSV writer
                configWriter.writerows(plotLayout)

        # Layout of the main window, used to create all the graphs and UI elements
        layout = CustomGridLayout(running, numChannels, plotDataProcesses, plotLayout, configFilename, connectionPipe, commandWriterPipe, startupCommandsFilename, sRCommandResponsePipe, saveDataQueue, xAxisLength, regDumpFilename)

        # Puts the graphs and UI into the main window for display
        mainWidget = QWidget()
        mainWidget.setLayout(layout)
        self.setCentralWidget(mainWidget)

    def closeEvent(self, _):

        QApplication.closeAllWindows() # Used to close any extra windows (such as cue or save data) that may have been opened

class CustomGridLayout(QGridLayout):

    def __init__(self, running, numChannels, plotDataProcesses, plotLayout, configFilename, connectionPipe, commandWriterPipe, startupCommandsFilename, sRCommandResponsePipe, saveDataQueue, xAxisLength, regDumpFilename):

        self.parent = super() # Needed later to add elements to layout
        self.parent.__init__()

        
        labels = [str(d[0]) for d in plotDataProcesses] # Extracts the names of the graphs for the dropdown menu

        # Sets maximum number of plots that can be shown at once, one column can't ever show more than half the graphs or more than 8 graphs
        normalMaxNumPlots = 8
        maxNumPlots = min(normalMaxNumPlots, int(len(plotDataProcesses) / 2))

        current = [] # 2d array containing arrays representing each column, contains current plot data process objects being shown, used to update plots from dropdown menu
        initalPlots = [] # 2d array containing arrays representing each column, used to fill plot columns with intial plot objects
        plotDropdowns = [] # 2d array containing arrays representing each column, contains dropdown menus corresponding with each graph containing all graph options

        for column in plotLayout: 
            # Each sublist repersents a column
            currentSublist = []
            initalPlotsSublist = []
            plotDropdownsSublist = []

            for plotNum in column:
                currentSublist.append(plotDataProcesses[plotNum])

                plot = guiPlots.CustomPlotWidget(running, plotDataProcesses[plotNum][1], plotDataProcesses[plotNum][0]) # Creates plot widget from a DataProcess
                plot.startRedraw()
                initalPlotsSublist.append(plot)

                dd = QComboBox() # Creates the starting dropdown menue
                dd.addItems(labels) # Adds the graph names to the dropdown menu
                dd.setCurrentIndex(plotNum) # Sets the item that it should start on, must come before connecting 'currentIndexChanged'
                plotDropdownsSublist.append(dd)

            current.append(currentSublist)
            initalPlots.append(initalPlotsSublist)
            plotDropdowns.append(plotDropdownsSublist)
                

        plotColumn0 = guiPlots.PlotColumn(initalPlots[0], 0, maxNumPlots) # Creates a plot column from a list of plots, an index and the max number of plots
        plotColumn1 = guiPlots.PlotColumn(initalPlots[1], 1, maxNumPlots)

        columnDropdowns0 = guiOptions.ColumnDropdowns(running, plotDropdowns[0], plotColumn0, plotDataProcesses, labels, current, maxNumPlots)
        columnDropdowns1 = guiOptions.ColumnDropdowns(running, plotDropdowns[1], plotColumn1, plotDataProcesses, labels, current, maxNumPlots)

        columnDropdownsLayout = QVBoxLayout()
        columnDropdownsLayout.addWidget(columnDropdowns0)
        columnDropdownsLayout.addWidget(columnDropdowns1)

        combindedPlotColumnLayout = QHBoxLayout()
        combindedPlotColumnLayout.addWidget(plotColumn0)
        combindedPlotColumnLayout.addWidget(plotColumn1)

        saveDataMenuButton = guiData.SaveDataMenuButton(running)

        saveDataWriter = guiData.SaveDataWriter(running, numChannels, saveDataQueue, saveDataMenuButton)
        saveDataWriter.startSaveDataWriter() # Not in its own process as implmentation would be complicated and it is the only demanding task on the main proces

        chatWindow = guiOptions.ChatWindow(commandWriterPipe, startupCommandsFilename, sRCommandResponsePipe)
        chatWindow.startUpdate()

        regDump = guiOptions.RegDump(regDumpFilename, chatWindow)

        startStop = guiOptions.StartStop(running, connectionPipe, saveDataMenuButton, chatWindow, regDump)
        cueSystemButton = guiCue.CueSystemButton(running, startStop)

        xAxisResizer = guiOptions.XAxisResizer(plotDataProcesses, xAxisLength)

        layoutSaver = guiOptions.LayoutSaver(configFilename, columnDropdowns0, columnDropdowns1, chatWindow)

        resetButton = guiOptions.PyserialReset(running, startStop, connectionPipe, chatWindow)

        optionsRowLayout = QHBoxLayout()
        optionsRowLayout.addWidget(saveDataMenuButton)
        optionsRowLayout.addWidget(cueSystemButton)
        optionsRowLayout.addWidget(startStop)
        optionsRowLayout.addWidget(xAxisResizer)
        optionsRowLayout.addWidget(layoutSaver)
        optionsRowLayout.addWidget(regDump)
        optionsRowLayout.addWidget(resetButton)

        optionsLayout = QVBoxLayout()
        optionsLayout.addLayout(optionsRowLayout)
        optionsLayout.addLayout(columnDropdownsLayout)

        optionsChatLayout = QHBoxLayout()
        optionsChatLayout.addLayout(optionsLayout, 3) # The second param on this line/next line is the stretch. Thus 3/1 gives 75% of the space to the options and 25% to chat
        optionsChatLayout.addWidget(chatWindow, 1)

        self.parent.addLayout(combindedPlotColumnLayout, 0, 0)
        self.parent.addLayout(optionsChatLayout, 1, 0)
        
        self.parent.addWidget(saveDataWriter, 2, 0) # SaveDataWriter hides itself and is only attached to be in the event loop

        current.append([columnDropdowns0, columnDropdowns1]) # Last item in current is list of ColumnDropdowns so they can reference each other

        sleep(2) # Program has to wait for other processes to connect to device before checking
        # 2s wait seems to work but if auto connection is failing but manually connecting works, try making the sleep longer
        startStop.connect("Automatic Connection Attempt Failed") # Automatically clicks "connect" button, gives unique error message on failure
        

def main(port):
    app = QApplication(sys.argv)
    main = MainWindow(port)
    main.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", help="Chip Port Name, /dev/cu.*")
    args = parser.parse_args()
    main(args.port)