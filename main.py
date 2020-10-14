import os
import sys
import numpy as np
import multiprocessing as mp
from time import sleep
from random import randint
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QGridLayout, QVBoxLayout, QWidget, QComboBox
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt, QTimer, QProcess
from pyqtgraph import PlotWidget, plot, mkPen

class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.setWindowTitle("Ear EEG GUI")

        numGraphs = 8 # Number of graphs to create, will probally end at 16

        possWidgets = []

        colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'] # Background colors of the graphs, currently used as otherwise all graphs would look identical

        # Currently creates 'numGraphs' identical test graphs, eventually each graph will be created individually
        for i in range(numGraphs): 
            dataProcess = SampleDataProcess()
            p = mp.Process(target=dataProcess.startUpdateData)
            p.daemon = True
            p.start()

            plotWidget = CustomPlotWidget(dataProcess, colors[i % len(colors)])
            plotWidget.startRedraw()
            possWidgets.append((i, plotWidget)) # First item in the tuple is supposed to be the name of the graph, is currently just its index

        layout = CustomGridLayout(possWidgets)

        mainWidget = QWidget()
        mainWidget.setLayout(layout)

        self.setCentralWidget(mainWidget)

class CustomGridLayout(QGridLayout):

    def __init__(self, possWidgets):

        self.parent = super()
        self.parent.__init__()
        self.possWidgets = possWidgets

        self.lables = [str(w[0]) for w in self.possWidgets] # Extracts the names of the graphs for the dropdown menu

        # Creates the dropdown menues
        d0 = QComboBox()
        d1 = QComboBox()
        d2 = QComboBox()
        d3 = QComboBox()

        d0.addItems(self.lables) # Adds the graph names to the dropdown menu
        d0.setCurrentIndex(0) # Sets the item that it should start on, must come before connecting 'currentIndexChanged'
        d0.currentIndexChanged.connect(self.changeWidget0) # Sets function to call when a user selects a different item from dropdown menu

        d1.addItems(self.lables)
        d1.setCurrentIndex(1)
        d1.currentIndexChanged.connect(self.changeWidget1)

        d2.addItems(self.lables)
        d2.setCurrentIndex(2)
        d2.currentIndexChanged.connect(self.changeWidget2)

        d3.addItems(self.lables)
        d3.setCurrentIndex(3)
        d3.currentIndexChanged.connect(self.changeWidget3)

        # Adds plots as 'DropdownPlotCombo' which is a 'VBoxLayout' containing both dropdown menu and plot
        self.parent.addWidget(DropdownPlotCombo(d0 ,self.possWidgets[0][1]), 0, 0)
        self.parent.addWidget(DropdownPlotCombo(d1 ,self.possWidgets[1][1]), 0, 1)
        self.parent.addWidget(DropdownPlotCombo(d2 ,self.possWidgets[2][1]), 1, 0)
        self.parent.addWidget(DropdownPlotCombo(d3 ,self.possWidgets[3][1]), 1, 1)

        # Sets grid up so all rows and columns will be of equal size
        self.parent.setColumnStretch(0, 1) 
        self.parent.setColumnStretch(1, 1)
        self.parent.setRowStretch(0, 1)
        self.parent.setRowStretch(1, 1)

        self.current = [self.possWidgets[0], self.possWidgets[1], self.possWidgets[2], self.possWidgets[3]] # Keeps track of currently displayed widgets

    # Called when the selected value in dropdown 0 is changed
    def changeWidget0(self, idx):
        self.changeWidgetHelper(idx, 0)

    def changeWidget1(self, idx):
        self.changeWidgetHelper(idx, 1)

    def changeWidget2(self, idx):
        self.changeWidgetHelper(idx, 2)

    def changeWidget3(self, idx):
        self.changeWidgetHelper(idx, 3)
    
    def changeWidgetHelper(self, widgetIdx, loc):

        newWidget = self.possWidgets[widgetIdx]
        row, col = int(loc / 2), int(loc % 2) # 0 = (0, 0), 1 = (0, 1), 2 = (1, 0), 3 = (1, 1)

        if newWidget in self.current: # If the graph is already being displayed swap the postion of the new graph and graph currently in the box

            # Primary refers to where the just selected graph will go, secondary refers to where the graph currently in the box will go
            oldSecondaryLoc = self.current.index(newWidget)
            secondaryRow = int(oldSecondaryLoc / 2)
            secondaryCol = int(oldSecondaryLoc % 2)

            primary = self.itemAtPosition(row, col).widget()
            secondary = self.itemAtPosition(secondaryRow, secondaryCol).widget()

            primary.tradePlot(secondary) # Swaps the plots

            # Updates the secondary dropdown to the correct value
            secondaryDrop = secondary.getDropdown()
            secondaryDrop.blockSignals(True)
            secondaryDrop.setCurrentIndex(self.possWidgets.index(self.current[loc]))
            secondaryDrop.blockSignals(False)

            # Updates the currently displayed widgets
            self.current[oldSecondaryLoc] = self.current[loc]
            self.current[loc] = newWidget

        else: # If the newly selected graph isn't already on the screen it just displays it

            curr = self.itemAtPosition(row, col).widget()
            curr.swapOutPlot(newWidget[1])
            self.current[loc] = newWidget

class DropdownPlotCombo(QWidget):

    def __init__(self, dropdown, plot):

        super().__init__()
        self.layout = QVBoxLayout()

        self.dropdown = dropdown
        self.plot = plot

        self.layout.addWidget(self.dropdown)
        self.layout.addWidget(self.plot)

        self.setLayout(self.layout)

    # Used to display a plot that is not currently on the screen
    def swapOutPlot(self, newPlot):
        # This line stops the widget from displaying, only thing that works here but supposedly can sometimes produce strange behavior
        # Possibly does the same thing as hide but I was worried hide would end up duplicating objects, couldn't find answer online
        self.plot.setParent(None)

        self.plot = newPlot
        self.layout.addWidget(self.plot)
    
    # Used to trade the plot currently in this object with a plot in another 'DropdownPlotCombox' object
    def tradePlot(self, dropdownPlotCombo):

        # Swaps plot objects
        otherPlot = dropdownPlotCombo.plot
        dropdownPlotCombo.plot = self.plot
        self.plot = otherPlot

        # See above comment about setting parent to None
        self.plot.setParent(None)
        dropdownPlotCombo.plot.setParent(None)

        self.layout.addWidget(self.plot)
        dropdownPlotCombo.layout.addWidget(dropdownPlotCombo.plot)

    def getDropdown(self):
        return self.dropdown

    def getPlot(self):
        return self.plot

# Graphs data given and updated by dataProcess
class CustomPlotWidget(PlotWidget):

    def __init__(self, dataProcess, color):

        super().__init__()
        self.setBackground(color) # Used to distinguish identical plots
        self.dataProcess = dataProcess

        self.refreshRate = 25 # How fast to redraw graph in milliseconds, currently not a parameter as will probably be same for every graph

        self.pen = mkPen(color=(0,0,0), width=3) # Sets color and size of line drawn on graph

        x, y = self.dataProcess.getData()

        self.data_line = self.plot(x, y, pen=self.pen)

    # Starts the redrawing of the plot every 'refreshRate' millseconds
    def startRedraw(self):

        self.timer = QTimer()
        self.timer.setInterval(self.refreshRate)
        self.timer.timeout.connect(self.redrawPlot)
        self.timer.start()

    # Redraws plot with data recived from dataProcess
    def redrawPlot(self):

        x, y = self.dataProcess.getData()
        self.data_line.setData(x, y)

# Abstract class defining methods needed in all data processes, each distinct graph will have an implementation of this
class DataProcess():

    # Starts a loop to call the updateData function 
    def startUpdateData(self):
        raise Exception("Child class must implement this method")

    # Recalculates the graphical data to return based on the raw input
    def updateData(self):
        raise Exception("Child class must implement this method")

    # Returns the data neeeded to redraw the graph
    # This method will likely be the same for all children but isn't defined here so all variables remain in the child class
    def getData(self):
        raise Exception("Child class must implement this method")

# Data process for a simple sine wave
class SampleDataProcess(DataProcess):
    
    def __init__(self):

        npX = np.arange(0, 1, 0.01)
        npY = np.sin(4 * np.pi * npX)

        # These must be multiprocessing arrays so the data can be shared back to the process drawing the graphs
        self.x = mp.Array('d', list(npX))
        self.y = mp.Array('d', list(npY))        

    def startUpdateData(self):

        while True:
            self.updateData()
            # This sleep will likely not normally be needed (unless we want to cap refresh speed) 
            # Needed here as the sine wave progresses a fixed amount every update
            # This is very different than it will be for real data where progression is based on the calculation run on actual live data coming in
            sleep(0.05)

    def updateData(self):
        for idx, val in enumerate(self.x):
            self.x[idx] = val + 0.01

        # Old method of progressing sine wave, didn't work on the multiprocess safe arrays
        # self.x.append(self.x[-1] + 0.01)
        # self.x = self.x[1:]

        tmp = self.y[0]
        for idx in range(len(self.y) - 1):
            self.y[idx] = self.y[idx + 1]
        self.y[-1] = tmp

        # Old method of progressing sine wave, didn't work on the multiprocess safe arrays
        # self.y.append(self.y[0])
        # self.y = self.y[1:]

    def getData(self):
        # [:] needed to extract array from multiprocessing.Array
        return self.x[:], self.y[:]


def main():

    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

# OLD NOTES:
# Over all very nice. I think this is a great start.
# Next features to add should be:
#       - Plotting 4 channels of data at a time
#       - Generate 16 channels of data and adding a few drop down boxes so that we can view 4 of these 16 channels
#       - Adding an option to save data to a file (and saving this dummy data to a file)
# 
# Some notes:
#       - We'll probably want to split the math (the sin waves) into a seperate object/class so that we can hot swap it with the EEG data stream
#       - This way we can just give the plot widgets access to a queue and have them plot whatever is coming out of the queue