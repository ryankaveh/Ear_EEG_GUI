import os
import re
from csv import writer
from time import sleep, time

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton,QLineEdit, QScrollArea
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import QTimer, QRegExp

import guiPlots

class StartStop(QWidget):

    def __init__(self, running, connectionPipe, saveDataMenuButton, chatWindow, regDump):

        super().__init__()

        self.running = running
        self.connectionPipe = connectionPipe
        self.saveDataMenuButton = saveDataMenuButton
        self.chatWindow = chatWindow
        self.regDump = regDump
        layout = QHBoxLayout()

        self.connectButton = QPushButton("Connect")
        self.connectButton.clicked.connect(lambda: self.connect()) # Lambda needed so parameters revert to defaults, connect send a boolean instead of no params

        self.startButton = QPushButton("Start")
        self.startButton.clicked.connect(self.start)
        self.startButton.setEnabled(False)
        self.startButton.hide()

        self.stopButton = QPushButton("Stop")
        self.stopButton.clicked.connect(self.stop)
        self.stopButton.setEnabled(False)
        self.stopButton.hide()

        layout.addWidget(self.connectButton, 1)
        layout.addWidget(self.startButton, 1)
        layout.addWidget(self.stopButton, 1)

        self.setLayout(layout)

        self.cueSystem = None
        self.synced = None
        self.connected = False
    
    def start(self):

        self.chatWindow.commandWriter.sendStartCommand()

        self.running.value = True
        self.saveDataMenuButton.setChangeable(False)
        self.startButton.setEnabled(False)
        self.stopButton.setEnabled(True)
        self.regDump.disable()

        if self.cueSystem:
            self.cueSystem.startStopSync.setEnabled(False)
        if self.synced:
            self.cueSystem.runTest()

        self.chatWindow.addMessage("Streaming Started")

    def stop(self):

        self.running.value = False
        self.saveDataMenuButton.setChangeable(True)
        self.stopButton.setEnabled(False)
        self.startButton.setEnabled(True)
        self.regDump.enable()

        if self.cueSystem:
            self.cueSystem.startStopSync.setEnabled(True)
        if self.synced:
            self.cueSystem.stopTest()

        self.chatWindow.commandWriter.sendStopCommand()

        self.chatWindow.addMessage("Streaming Stopped")

    def connect(self, failureMessage="No Device Found"): # failureMessage used to modify message when automatic connection is attempted (currently on startup)

        if self.connectionPipe.poll():
            self.chatWindow.addMessage("Connection Success")
            print("Connection Success")
            self.connected = True
            self.connectButton.hide()
            self.startButton.setEnabled(True)
            self.startButton.show()
            self.stopButton.show()
            self.chatWindow.commandWriter.runStartupCommands()
            self.chatWindow.commandWriter.enable()
            self.regDump.enable()
        else:
            self.chatWindow.addMessage(failureMessage)
            print(failureMessage)

    def setCueSync(self, cueSystem, syncState):
        if syncState and (not self.connected): # Cannot sync start/stop before connection is made
            return False # Failure
        self.synced = syncState
        self.cueSystem = cueSystem
        return True # Success

class ChatWindow(QWidget):

    def __init__(self, commandWriterPipe, startupCommandsFilename, sRCommandResponsePipe):

        super().__init__()

        self.sRCommandResponsePipe = sRCommandResponsePipe

        self.refreshRate = 200 # Refresh rate in ms, controls how often chat is updated

        self.regTimer = QTimer()
        self.regTimer.setInterval(1) # Checks every 1 ms
        self.regTimer.timeout.connect(self.collectRegDump)
        self.regDumpValues = [] # Used to store values when performing a reg dump

        layout = QVBoxLayout()
        self.scrollArea = QScrollArea() # Will make it so the messages are scrollable
        self.scrollArea.setWidgetResizable(True)
        layout.addWidget(self.scrollArea)
        
        messageBox = QWidget(self.scrollArea)
        self.scrollArea.setWidget(messageBox)
        self.scrollArea.verticalScrollBar().rangeChanged.connect(self.scrollToBottom)
        messageBoxLayout = QVBoxLayout()

        self.messages = QLabel("GUI Intialized")
        self.messages.setWordWrap(True)
        messageBoxLayout.addWidget(self.messages)
        messageBox.setLayout(messageBoxLayout)

        self.commandWriter = CommandWriter(commandWriterPipe, startupCommandsFilename, self)
        layout.addWidget(self.commandWriter)

        self.setLayout(layout)

    def startUpdate(self):

        self.timer = QTimer()
        self.timer.setInterval(self.refreshRate)
        self.timer.timeout.connect(self.updateChat)
        self.timer.start()

    def updateChat(self):

        if self.sRCommandResponsePipe.poll():
            response = self.sRCommandResponsePipe.recv()
            self.addMessage(str(response))

    def addMessage(self, newText):

        self.messages.setText(self.messages.text() + "\n" + newText)

    def scrollToBottom(self):

        scrollBar = self.scrollArea.verticalScrollBar()
        scrollBar.setSliderPosition(scrollBar.maximum())

    def getAllRegValues(self, regNums):

        self.timer.stop()

        self.regDumpValues = ""

        self.regTimer.start()

        for num in regNums:
            self.commandWriter.sendRegReadCommand(num)
            sleep(0.01) # Sends command every 10 ms

    def collectRegDump(self):

        if self.sRCommandResponsePipe.poll():
            response = self.sRCommandResponsePipe.recv()
            self.regDumpValues.append(response)

class CommandWriter(QWidget):

    def __init__(self, commandWriterPipe, startupCommandsFilename, chatWindow):

        super().__init__()

        self.enabled = False

        self.commandWriterPipe = commandWriterPipe
        self.startupCommandsFilename = startupCommandsFilename
        self.chatWindow = chatWindow

        layout = QHBoxLayout()

        self.commandInput = QLineEdit()
        self.commandInput.returnPressed.connect(self.sendCommand)

        layout.addWidget(self.commandInput)

        self.setLayout(layout)

    def enable(self):

        self.enabled = True

    def sendCommand(self):

        if self.enabled:
            text = str.lower(self.commandInput.text())

            if self.badCommandFormat(text):
                return
            else:
                self.commandWriterPipe.send(text)
                self.chatWindow.addMessage("User: " + text)
                self.commandInput.clear()
        else:
            self.chatWindow.addMessage("Please Connect to a Device First")
        
    def sendStartCommand(self):

        self.commandWriterPipe.send("start")

    def sendStopCommand(self):

        self.commandWriterPipe.send("stop")

    def sendPyserialResetCommand(self):

        self.commandWriterPipe.send("pyserialReset")

    def sendRegReadCommand(self, regNum): # regNum should be a 2 digit string 00-99

        self.commandWriterPipe.send("read reg " + regNum)

    def runStartupCommands(self):

        if os.path.exists(self.startupCommandsFilename):
            print("Running Startup Commands")
            with open(self.startupCommandsFilename, 'r') as startupCommands:
                commands = startupCommands.read().splitlines()
                for com in commands:
                    if not self.badCommandFormat(com):
                        self.commandWriterPipe.send(com)
                        self.chatWindow.addMessage("Startup: " + com) 
        else:
            print("No Startup Commands File Found, Looking For: " + self.startupCommandsFilename)

    def badCommandFormat(self, text): # Returns true on a failure

        if re.search(r"^read reg", text) and not re.search(r"^read reg [0-9]{2}$", text):
            self.chatWindow.addMessage("Must follow format `read reg xx` where xx is 00-99")
            return True
        elif re.search(r"^write reg", text) and not re.search(r"^write reg [0-9]{2} [0-9a-f]{4}$", text):
            self.chatWindow.addMessage("Must follow format `write reg xx yyyy` where xx is 00-99 and yyyy is 0000-ffff")
            return True
        else:
            return False


class XAxisResizer(QWidget):

    def __init__(self, plotDataProcesses, currXAxisLength):

        super().__init__()

        self.plotDataProcesses = plotDataProcesses
        self.currXAxisLength = currXAxisLength

        layout = QHBoxLayout()

        self.xAxisLength = QLineEdit()
        self.xAxisLength.setValidator(QRegExpValidator(QRegExp("[0-9]*")))

        self.xAxisResizeButton = QPushButton("Resize")
        self.xAxisResizeButton.clicked.connect(self.resize)

        layout.addWidget(self.xAxisLength)
        layout.addWidget(self.xAxisResizeButton)

        self.setLayout(layout)

    def resize(self):

        newLength = int(self.xAxisLength.text())
        for dataProcess in self.plotDataProcesses:
            dataProcess[1].resizeXAxis(newLength)

class LayoutSaver(QWidget):

    def __init__(self, configFilename, columnDropdowns0, columnDropdowns1, chatWindow):

        super().__init__()

        self.configFilename = configFilename
        self.columnDropdowns = [columnDropdowns0, columnDropdowns1]
        self.chatWindow = chatWindow

        layout = QHBoxLayout()

        self.saveLayoutButton = QPushButton("Save Current Layout")
        self.saveLayoutButton.clicked.connect(self.saveLayout)

        layout.addWidget(self.saveLayoutButton)

        self.setLayout(layout)

    def saveLayout(self):

        plotLayout = []

        for colDropdown in self.columnDropdowns:
            plotLayoutSublist = []
            for dropdown in colDropdown.dropdowns:
                if dropdown is not None:
                    plotLayoutSublist.append(dropdown.currentIndex())
            plotLayout.append(plotLayoutSublist)

        with open(self.configFilename, 'w') as config:
            configWriter = writer(config) # CSV writer
            configWriter.writerows(plotLayout)

        self.chatWindow.addMessage("Current Layout Saved as Default")

class RegDump(QWidget):

    def __init__(self, regDumpFilename, chatWindow):

        super().__init__()

        self.regDumpFilename = regDumpFilename
        self.chatWindow = chatWindow

        layout = QHBoxLayout()

        self.regDumpButton = QPushButton("Save All Registers")
        self.regDumpButton.clicked.connect(self.dumpRegs)
        self.regDumpButton.setEnabled(False)

        layout.addWidget(self.regDumpButton)

        self.setLayout(layout)

    def enable(self):

        self.regDumpButton.setEnabled(True)

    def disable(self):

        self.regDumpButton.setEnabled(False)

    def dumpRegs(self):

        regNums = ["0" + str(i) for i in range(10)] + [str(i) for i in range(10,64)]
        self.chatWindow.getAllRegValues(regNums)
        sleep(1) # Sleeps to make sure all responses have been received

        self.chatWindow.regTimer.stop()
        self.chatWindow.timer.start()
        regDumpValues = self.chatWindow.regDumpValues
        print(regDumpValues)

        with open(self.regDumpFilename, 'a') as regDump:
            regDump.write("Time Dumped: " + str(time()))
            for idx, regVal in enumerate(regDumpValues):
                regDump.write(regNums[idx] + regVal)

# Class containing all of the dropdown menues corrosponding to a certain PlotColumn
class ColumnDropdowns(QWidget):

    def __init__(self, running, startingDropdowns, plotColumn, plotDataProcesses, lables, current, maxNumPlots):

        super().__init__()

        self.running = running
        self.dropdowns = startingDropdowns
        self.plotColumn = plotColumn # PlotColumn that corrosponds to this set of dropdown menus
        self.plotDataProcesses = plotDataProcesses
        self.lables = lables
        self.current = current
        self.maxNumPlots = maxNumPlots

        self.layout = QHBoxLayout()

        self.numPlots = len(startingDropdowns)
        self.screenIdx = self.plotColumn.getScreenIdx() # Corrosponds to index on screen, used to select the right column when indexing into current

        sizeDropdown = QComboBox()
        sizeDropdown.addItems(str(val) for val in range(self.maxNumPlots + 1))
        sizeDropdown.setCurrentIndex(self.numPlots)
        sizeDropdown.currentIndexChanged.connect(self.changeSize)
        self.layout.addWidget(sizeDropdown, 1)

        # Uses lambda function to connect each intial dropdown to changePlotHelper with the right parameters and then adds it to the layout
        for idx, drop in enumerate(self.dropdowns):
            drop.currentIndexChanged.connect(lambda plotDataProcessesIdx, plotIdx=idx: self.changePlotHelper(plotDataProcessesIdx, plotIdx))
            self.layout.addWidget(drop, 1)
        
        # Fills dropdowns list so that indexing outside of the current self.numPlots value can be done
        for _ in range(self.maxNumPlots - self.numPlots):
            self.dropdowns.append(None)

        self.setLayout(self.layout)

    # Called when the size dropdown changes value
    def changeSize(self, newSize):

        if self.numPlots == 0:
            self.plotColumn.show()

        sizeDiff = newSize - self.numPlots

        # This section is called when the size goes down, it removes the extra dropdown menus and then tells the PlotColumn to reduce its size
        if sizeDiff < 0:
            for idx in range(newSize, self.numPlots):
                self.layout.removeWidget(self.dropdowns[idx])
                self.dropdowns[idx].deleteLater()
                self.dropdowns[idx] = None

            del self.current[self.screenIdx][newSize:self.numPlots]

            self.plotColumn.shrink(newSize)

            if newSize == 0:
                self.plotColumn.hide()
        
        # This section is called when the size goes up
        # It starts by finding the next sizeDiff DataProcesses that aren't already on screen and creates plot widgets from them
        # It then adds the neccesary dropdown menus and finally tells the PlotColumn to add these new plot widgets
        else:
            newPlots = []
            indices = [] # Used to set the intial value of the dropdown menus
            idx = 0
            while len(newPlots) < sizeDiff:
                possData = self.plotDataProcesses[idx]
                exists = False
                for col in self.current:
                    if possData in col:
                        exists = True
                if not exists:
                    newPlot = guiPlots.CustomPlotWidget(self.running, possData[1], possData[0])
                    newPlot.startRedraw()
                    newPlots.append(newPlot)
                    indices.append(idx)
                    self.current[self.screenIdx].append(possData)
                idx += 1

            for idx in range(self.numPlots, newSize):
                newDrop = QComboBox()
                newDrop.addItems(self.lables)
                newDrop.setCurrentIndex(indices[idx - self.numPlots])
                newDrop.currentIndexChanged.connect(lambda plotDataProcessesIdx, plotIdx=idx: self.changePlotHelper(plotDataProcessesIdx, plotIdx))

                self.dropdowns[idx] = newDrop
                self.layout.addWidget(self.dropdowns[idx], 1)

            self.plotColumn.grow(newSize, newPlots)
        
        self.numPlots = newSize
    
    # Called when the user changes any of the plots with the dropdown menu
    def changePlotHelper(self, plotDataProcessesIdx, plotIdx):

        newPlotData = self.plotDataProcesses[plotDataProcessesIdx]

        # Checks if the desired plot already exists anywhere on screen
        exists = False
        colIdx = -1 # Equiv to self.screenIdx but for the desired plot (that could be in any column onscreen currently)
        for idx, col in enumerate(self.current):
            if newPlotData in col:
                exists = True
                colIdx = idx

        if exists: # If the graph is already being displayed on screen swap the postion of the new graph and graph currently in the way

            # Primary refers to where the just selected graph will go, secondary refers to where the graph currently in the box will go
            oldSecondaryLoc = self.current[colIdx].index(newPlotData)

            secondary = self.current[-1][colIdx]

            self.plotColumn.tradePlot(plotIdx, secondary.plotColumn, oldSecondaryLoc) # Swaps the plots

            # Updates the secondary dropdown menu to the correct value
            secondaryDrop = secondary.dropdowns[oldSecondaryLoc]
            secondaryDrop.blockSignals(True)
            secondaryDrop.setCurrentIndex(self.plotDataProcesses.index(self.current[self.screenIdx][plotIdx]))
            secondaryDrop.blockSignals(False)

            # Updates the current
            self.current[colIdx][oldSecondaryLoc] = self.current[self.screenIdx][plotIdx]
            self.current[self.screenIdx][plotIdx] = newPlotData

        else: # If the newly selected graph isn't already on the screen it just displays it

            newPlot = guiPlots.CustomPlotWidget(self.running, newPlotData[1], newPlotData[0])
            newPlot.startRedraw()
            self.plotColumn.swapOutPlot(plotIdx, newPlot)
            self.current[self.plotColumn.getScreenIdx()][plotIdx] = newPlotData

class PyserialReset(QWidget):

    def __init__(self, running, startStop, connectionPipe, chatWindow):

        super().__init__()

        self.running = running
        self.startStop = startStop
        self.connectionPipe = connectionPipe
        self.chatWindow = chatWindow

        layout = QHBoxLayout()

        self.resetButton = QPushButton("Reset")
        self.resetButton.clicked.connect(self.reset)

        layout.addWidget(self.resetButton)

        self.setLayout(layout)

    def reset(self):

        if self.running.value:
            self.startStop.stop()

        self.chatWindow.commandWriter.sendPyserialResetCommand()
        self.chatWindow.addMessage("Pyserial Connection Reset")


        
