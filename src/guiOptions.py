from csv import writer

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QPushButton,QLineEdit, QScrollArea
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import QTimer, QRegExp

import guiPlots

class StartStop(QWidget):

    def __init__(self, running, connectionPipe, saveDataMenuButton, chatWindow):

        super().__init__()

        self.running = running
        self.connectionPipe = connectionPipe
        self.saveDataMenuButton = saveDataMenuButton
        self.chatWindow = chatWindow
        layout = QHBoxLayout()

        self.connectButton = QPushButton("Connect")
        self.connectButton.clicked.connect(self.connect)

        self.startButton = QPushButton("Start")
        self.startButton.clicked.connect(self.start)
        self.startButton.setDisabled(True)
        self.startButton.hide()

        self.stopButton = QPushButton("Stop")
        self.stopButton.clicked.connect(self.stop)
        self.stopButton.setDisabled(True)
        self.stopButton.hide()

        layout.addWidget(self.connectButton, 1)
        layout.addWidget(self.startButton, 1)
        layout.addWidget(self.stopButton, 1)

        self.setLayout(layout)

        self.cueSystem = None
        self.synced = None
        self.connected = False
    
    def start(self):

        self.chatWindow.commandWriter.sendStreamCommand()

        self.running.value = True
        self.saveDataMenuButton.setChangeable(False)
        self.startButton.setDisabled(True)
        self.stopButton.setDisabled(False)

        if self.cueSystem:
            self.cueSystem.startStopSync.setDisabled(True)
        if self.synced:
            self.cueSystem.runTest()

        self.chatWindow.addMessage("Streaming Started")

    def stop(self):

        self.running.value = False
        self.saveDataMenuButton.setChangeable(True)
        self.stopButton.setDisabled(True)
        self.startButton.setDisabled(False)

        if self.cueSystem:
            self.cueSystem.startStopSync.setDisabled(False)
        if self.synced:
            self.cueSystem.stopTest()

        self.chatWindow.commandWriter.sendStreamCommand()

        self.chatWindow.addMessage("Streaming Stopped")

    def connect(self, failureMessage="No Device Found"): # failureMessage used to modify message when automatic connection is attempted (currently on startup)

        if self.connectionPipe.poll():
            self.connected = True
            self.connectButton.hide()
            self.startButton.setDisabled(False)
            self.startButton.show()
            self.stopButton.show()
            self.chatWindow.commandWriter.enable()
            self.chatWindow.addMessage("Connection Success")
            print("Connection Success")
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

    def __init__(self, commandWriterPipe, sRCommandResponsePipe):

        super().__init__()

        self.sRCommandResponsePipe = sRCommandResponsePipe

        self.refreshRate = 200 # Chat will update every 200 ms

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

        self.commandWriter = CommandWriter(commandWriterPipe, self)
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

class CommandWriter(QWidget):

    def __init__(self, commandWriterPipe, chatWindow):

        super().__init__()

        self.enabled = False

        self.commandWriterPipe = commandWriterPipe
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
            text = self.commandInput.text()
            self.commandWriterPipe.send(text)
            self.chatWindow.addMessage("User: " + text)
            self.commandInput.clear()
        else:
            self.chatWindow.addMessage("Please Connect to a Device First")
        
    def sendStreamCommand(self):

        self.commandWriterPipe.send("stream")

class XAxisResizer(QWidget):

    def __init__(self, possPlotData, currXAxisLength):

        super().__init__()

        self.possPlotData = possPlotData
        self.currXAxisLength = currXAxisLength

        layout = QHBoxLayout()

        self.xAxisLength = QLineEdit()
        self.xAxisLength.setValidator(QRegExpValidator(QRegExp("[0-9]*")))

        self.xAxisResizeButton = QPushButton("Resize")
        self.xAxisResizeButton.clicked.connect(self.resize)
        #self.xAxisResizeButton.setDisabled(True) # TODO: setEnabled vs. setDisabled why do I use both

        layout.addWidget(self.xAxisLength)
        layout.addWidget(self.xAxisResizeButton)

        self.setLayout(layout)

    def resize(self):

        newLength = int(self.xAxisLength.text())
        for dataProcess in self.possPlotData:
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
        
# Class containing all of the dropdown menues corrosponding to a certain PlotColumn
class ColumnDropdowns(QWidget):

    def __init__(self, running, startingDropdowns, plotColumn, possPlotData, lables, current, maxNumPlots):

        super().__init__()

        self.running = running
        self.dropdowns = startingDropdowns
        self.plotColumn = plotColumn # PlotColumn that corrosponds to this set of dropdown menus
        self.possPlotData = possPlotData
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
            drop.currentIndexChanged.connect(lambda possPlotDataIdx, plotIdx=idx: self.changePlotHelper(possPlotDataIdx, plotIdx))
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
                possData = self.possPlotData[idx]
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
                newDrop.currentIndexChanged.connect(lambda possPlotDataIdx, plotIdx=idx: self.changePlotHelper(possPlotDataIdx, plotIdx))

                self.dropdowns[idx] = newDrop
                self.layout.addWidget(self.dropdowns[idx], 1)

            self.plotColumn.grow(newSize, newPlots)
        
        self.numPlots = newSize
    
    # Called when the user changes any of the plots with the dropdown menu
    def changePlotHelper(self, possPlotDataIdx, plotIdx):

        newPlotData = self.possPlotData[possPlotDataIdx]

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
            secondaryDrop.setCurrentIndex(self.possPlotData.index(self.current[self.screenIdx][plotIdx]))
            secondaryDrop.blockSignals(False)

            # Updates the current
            self.current[colIdx][oldSecondaryLoc] = self.current[self.screenIdx][plotIdx]
            self.current[self.screenIdx][plotIdx] = newPlotData

        else: # If the newly selected graph isn't already on the screen it just displays it

            newPlot = guiPlots.CustomPlotWidget(self.running, newPlotData[1], newPlotData[0])
            newPlot.startRedraw()
            self.plotColumn.swapOutPlot(plotIdx, newPlot)
            self.current[self.plotColumn.getScreenIdx()][plotIdx] = newPlotData
