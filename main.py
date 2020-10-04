import os
import sys
import numpy as np
from random import randint
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QGridLayout, QWidget
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt, QTimer
from pyqtgraph import PlotWidget, plot, mkPen


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle("Ear EEG GUI")

        layout = QGridLayout()

        w1 = CustomPlotWidget()
        w2 = CustomPlotWidget()

        w3 = Color('green')
        w3.setMinimumSize(w1.width(), w1.height())
        w4 = Color('purple')
        w4.setMinimumSize(w1.width(), w1.height())

        widgets = [w1, w2, w3, w4]

        for idx, w in enumerate(widgets):
            layout.addWidget(w, int(idx % 2), int(idx / 2))

        mainWidget = QWidget()
        mainWidget.setLayout(layout)

        self.setCentralWidget(mainWidget)


class Color(QWidget):

    def __init__(self, color, *args, **kwargs):
        super(Color, self).__init__(*args, **kwargs)
        self.setAutoFillBackground(True)
        
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(color))
        self.setPalette(palette)

class CustomPlotWidget(PlotWidget):

    def __init__(self, *args, **kwargs):
        super(CustomPlotWidget, self).__init__(*args, **kwargs)
        self.setBackground('w')
        self.pen = mkPen(color=(0,0,0), width=3)

        npX = np.arange(0, 1, 0.01)
        npY = np.sin(4 * np.pi * npX)

        self.x = list(npX)
        self.y = list(npY)

        self.data_line = self.plot(self.x, self.y, pen=self.pen)

        self.timer = QTimer()
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.update_plot_data)
        self.timer.start()

    def update_plot_data(self):

        self.x.append(self.x[-1] + 0.01)
        self.x = self.x[1:]

        self.y.append(self.y[0])
        self.y = self.y[1:]

        self.data_line.setData(self.x, self.y)


def main():
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()