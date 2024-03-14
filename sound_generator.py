#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, time
import numpy as np, pyaudio

class SoundGenerator():
	SINE = 0
	SINE2 = 1
	SINE3 = 2
	TRIANGLE = 3
	SQUARE = 4

	def __init__(self, fs=44100):
		self.newFrequency = None
		self.newVolume = 0
		self.fs = float(fs)
		self.waveFormType = self.SINE
		self.volume = 0.3
		self.frequency = 0
		self.deltaPhase = 0
		self.stream = None
		self.p = pyaudio.PyAudio()

	def start(self, fs=None):
		if self.stream == None:
			if fs != None:
				self.fs = float(fs)
			self.outbuf = np.zeros(1000).astype(np.float32)
			self.bufferPreRoll = 10
			self.phase = 0
			self.stream = self.p.open(format=pyaudio.paFloat32, channels=1, rate=int(self.fs), output=True, stream_callback=self.callback, frames_per_buffer=1000)
			self.stream.start_stream()

	def callback(self, in_data, frame_count, time_info, status):
		if self.bufferPreRoll:
			self.bufferPreRoll-=1
			return (self.outbuf, pyaudio.paContinue)

		for n in range(frame_count):
			if self.waveFormType == self.SINE:
				# simple sinewave
				self.outbuf[n] = self.volume * np.sin(self.phase)

			elif self.waveFormType == self.SINE2:
				# squared and alternated sinewave
				self.outbuf[n] = self.volume * np.sin(self.phase)**2 * (1 if self.phase > np.pi else -1)

			elif self.waveFormType == self.SINE3:
				# cubed sinewave
				self.outbuf[n] = self.volume * np.sin(self.phase)**3

			elif self.waveFormType == self.TRIANGLE:
				# triangle waveform
				if self.phase <= 0.5*np.pi:
					self.outbuf[n] = self.volume * (self.phase/(0.5*np.pi))
				elif self.phase <= np.pi*1.5:
					self.outbuf[n] = self.volume * (2-(self.phase/(0.5*np.pi)))
				else:
					self.outbuf[n] = self.volume * (-4+(self.phase/(0.5*np.pi)))

			elif self.waveFormType == self.SQUARE:
				# square wave
				self.outbuf[n] = self.volume * (-1 if self.phase<np.pi else 1)

			# update phase for each sample
			self.phase+=self.deltaPhase
			if self.phase > 2*np.pi:
				self.phase-=2*np.pi

			# low pass filter for volume control
			if self.newVolume != None:
				self.volume, self.oldVolume = self.volume * 0.999 + self.newVolume * 0.001, self.volume
				if self.volume == self.oldVolume:
					self.volume, self.newVolume = self.newVolume, None

		return (self.outbuf, pyaudio.paContinue)

	def stop(self):
		if self.stream != None:
			self.stream.stop_stream()
			self.stream.close()
			self.stream = None

	def __del__(self):
		self.p.terminate()

	def isActive(self):
		if self.stream == None:
			return False
		return self.stream.is_active()

	def setFrequency(self, frequency):
		self.frequency = frequency
		self.deltaPhase = 2*np.pi*self.frequency/self.fs

	def setVolume(self, volume):
		self.newVolume = volume
		if not self.isActive():
			self.volume = volume

	def setWaveFormType(self, waveFormType):
		self.waveFormType = waveFormType

try:
	# sudo apt-get install python3-pyqt5
	# ~ raise("Uncomment this line is to want to force fallback to PyQt4 for testing")
	from PyQt5.QtGui import *
	from PyQt5.QtCore import *
	from PyQt5.QtWidgets import *
	PYQT_VERSION = 5
	print("Using PyQt5")
except:
	# sudo apt-get install python-qtpy python3-qtpy
	from PyQt4.QtGui import *
	from PyQt4.QtCore import *
	PYQT_VERSION = 4
	print("Using PyQt4")

class FrequencyPicker(QHBoxLayout):
	def __init__(self, unit="Hz", digitsNumber=6, decimals=2):
		QHBoxLayout.__init__(self)
		self.digitsNumber = digitsNumber
		self.decimals = decimals
		self.digits = {}
		self.digitChangedEvent = None
		self.addStretch()
		for i in range(self.digitsNumber-self.decimals-1, -self.decimals-1, -1):
			l = QLabel("0")
			l.setAlignment(Qt.AlignBottom)
			l.setObjectName("digit")
			l.setToolTip("Use scrollwheel on a digit to change it")
			l.wheelEvent = lambda event, i=i: self.wheelDigitEvent(event, i)
			self.addWidget(l)
			self.digits[i] = l
			if i == 0:
				l = QLabel(".")
				l.setAlignment(Qt.AlignBottom)
				l.setObjectName("digit")
				self.addWidget(l)
		l = QLabel(unit)
		l.setAlignment(Qt.AlignBottom)
		l.setObjectName("label")
		self.updateGreyness()
		self.addWidget(l)
		self.addStretch()

	def wheelDigitEvent(self, event, digit):
		def upDown(digit, inc):
			ret = False
			if digit >= (self.digitsNumber-self.decimals): return True
			digitValue = int(self.digits[digit].text())
			digitValue+=inc
			if digitValue>9:
				digitValue=0
				ret = upDown(digit+1, inc)
			elif digitValue<0:
				digitValue=9
				ret = upDown(digit+1, inc)
			if not ret:
				self.digits[digit].setText(str(digitValue))
			return ret

		if event.angleDelta().y() < 0:
			if digit >= self.firstSignificantDigit:
				if self.digits[digit].text() == "0" or self.digits[digit].text() == "1":
					return
			upDown(digit, -1) # decrement
		else:
			upDown(digit, +1) # increment

		for p in self.digits:
			if p < digit:
				self.digits[p].setText("0")
		self.updateGreyness()

		if self.digitChangedEvent != None:
			self.digitChangedEvent(self.value())

	def updateGreyness(self):
		style = "color: grey;"
		self.firstSignificantDigit = None
		for p in sorted(self.digits, reverse=True):
			if self.digits[p].text() != "0":
				style=""
				if self.firstSignificantDigit == None:
					self.firstSignificantDigit = p
			if p>0:
				self.digits[p].setStyleSheet(style)
		if self.firstSignificantDigit == None:
			self.firstSignificantDigit = p

	def value(self):
		frequency = 0
		for p in self.digits:
			frequency+=(10**p) * int(self.digits[p].text())
		return frequency

	def setValue(self, value):
		frequencyString = ("%0"+str(self.digitsNumber+1)+"."+str(self.decimals)+"f") % round(value, self.decimals);
		if len(frequencyString) > self.digitsNumber+1:
			frequencyString = "9" * self.digitsNumber
		digit = -self.decimals
		while frequencyString != "":
			frequencyString, digitString = frequencyString[:-1], frequencyString[-1:]
			if digitString.isdigit():
				self.digits[digit].setText(digitString)
				digit+=1
		self.updateGreyness()

class GUI(QWidget):
	def __init__(self):
		super(GUI, self).__init__()
		self.initUI()
		self.sound = SoundGenerator()
		self.setFrequency(100, updateFrequencyPicker=True)

	def enableSoundCardBtnClicked(self):
		if self.enableSoundCardBtn.isChecked():
			self.sound.setVolume(self.v.value() / 100.0)
			self.sound.start()
		else:
			self.sound.setVolume(0)
			self.soundOffTimer = QTimer()
			self.soundOffTimer.timeout.connect(self.soundOff)
			self.soundOffTimer.start(500)
			self.enableSoundCardBtn.setEnabled(False)

	def soundOff(self):
		self.sound.stop()
		self.enableSoundCardBtn.setEnabled(True)
		self.soundOffTimer.stop()
		del self.soundOffTimer

	def initUI(self):
		self.setStyleSheet("\
			QLabel { margin: 0px; padding: 0px; } \
			QSplitter::handle:vertical   { image: none; } \
			QSplitter::handle:horizontal { width:  2px; image: none; } \
			QLabel#digit { font-size: 40pt; padding-left: 0px; padding-right: 0px; } \
			QLabel#label { font-size: 30pt; } \
		");

		layout = QVBoxLayout(self)

		def mkQLabel(text=None, layout=None, alignment=Qt.AlignLeft, objectName=None):
			o = QLabel()
			if objectName:
				o.setObjectName(objectName)
			o.setAlignment(alignment)
			if text:
				o.setText(text)
			if layout != None:
				layout.addWidget(o)
			return o

		def mkButton(text, layout=None, function=None, gridPlacement=(0,0), gridSpan=(1,1), isCheckable=False):
			btn = QPushButton(text)
			btn.setFocusPolicy(Qt.TabFocus)
			btn.setCheckable(isCheckable)
			if function:
				btn.clicked.connect(function)
			if type(layout) == QGridLayout:
				layout.addWidget(btn, gridPlacement[0], gridPlacement[1], gridSpan[0], gridSpan[1])
			elif layout:
				layout.addWidget(btn)
			return btn

		self.frequencyPicker = FrequencyPicker(digitsNumber=8, decimals=3)
		self.frequencyPicker.digitChangedEvent = self.setFrequency
		layout.addLayout(self.frequencyPicker)

		self.f = QSlider(Qt.Horizontal)
		self.f.setToolTip("Adjust Frequency (logarithmically)")
		self.f.setMinimum(0)
		self.f.setMaximum(30000)
		self.f.value,    self.f._value    = lambda: 10**((self.f._value()+10000)/10000.0) * 2, self.f.value
		self.f.setValue, self.f._setValue = lambda f: self.f._setValue(0 if f<=0 else int(round(np.log10(f/2.0)*10000))-10000), self.f.setValue
		self.f.valueChanged.connect(self.frequencySliderMoved)
		layout.addWidget(self.f)

		self.v = QSlider(Qt.Horizontal)
		self.v.setToolTip("Adjust Volume")
		self.v.setMinimum(0)
		self.v.setMaximum(100)
		self.v.setValue(10)
		self.v.valueChanged.connect(lambda: self.sound.setVolume(self.v.value() / 100.0))
		layout.addWidget(self.v)

		self.radiobuttons = []
		self.radiobuttons.append(QRadioButton("&Sine"))
		self.radiobuttons.append(QRadioButton("Sine^&2"))
		self.radiobuttons.append(QRadioButton("Sine^&3"))
		self.radiobuttons.append(QRadioButton("&Triangle"))
		self.radiobuttons.append(QRadioButton("S&quare"))
		self.radiobuttons[0].setChecked(True)

		l = QHBoxLayout()
		self.buttonsgroup = QButtonGroup()
		self.buttonsgroup.buttonClicked.connect(lambda button: self.sound.setWaveFormType(button.waveType))
		for i, button in enumerate(self.radiobuttons):
			self.buttonsgroup.addButton(button)
			button.waveType = i
			l.addWidget(button)
		layout.addLayout(l)

		self.enableSoundCardBtn = mkButton("&Enable sound", layout, self.enableSoundCardBtnClicked, isCheckable=True)

		self.setWindowTitle("Sound Generator")
		self.show()
		self.setMaximumHeight(self.height())

	def frequencySliderMoved(self):
		frequency = self.f.value()
		self.frequencyPicker.setValue(frequency)
		self.sound.setFrequency(frequency)

	def setFrequency(self, frequency, updateFrequencyPicker=False):
		if updateFrequencyPicker:
			self.frequencyPicker.setValue(frequency)
		self.sound.setFrequency(frequency)
		self.f.blockSignals(True)
		self.f.setValue(frequency)
		self.f.blockSignals(False)

def main():
	app = QApplication(sys.argv)
	gui = GUI()
	app.installEventFilter(gui)
	ret = app.exec_()
	sys.exit(ret)

if __name__ == '__main__':
	main()

# clx.freeshell.org 2021
