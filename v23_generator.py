#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, time, queue
import numpy as np, pyaudio

class SoundGenerator():
	def __init__(self, fs=44100):
		self.newFrequency = None
		self.newVolume = 0
		self.fs = float(fs)
		self.volume = 0
		self.frequency = 0
		self.deltaPhase = 0
		self.encoding = 'ascii'
		self.baudRate = 1200
		self.frequencyIdle = 1500
		self.frequencyMark = 1300 # 1
		self.frequencySpace = 2100 # 0
		self.bits = 7
		self.parity = True
		self.parityOdd = False
		self.stopBits = 1
		self.stream = None
		self.p = pyaudio.PyAudio()
		self.queue = queue.Queue()
		self.waitSamples = 0

		self.output_device_index = -1
		for i in range(self.p.get_device_count()):
			name = self.p.get_device_info_by_index(i)['name']
			if 'pipewire' in name:
				self.output_device_index = i
			print("%2d %s%s" % (i, "*" if self.output_device_index == i else "", name))

	def start(self, fs=None):
		if self.stream == None:
			if fs != None:
				self.fs = float(fs)
			self.outbuf = np.zeros(1000).astype(np.float32)
			self.bufferPreRoll = 10
			self.phase = 0
			self.setFrequency(self.frequencyIdle)
			self.waitSamples = self.fs
			self.stream = self.p.open(format=pyaudio.paFloat32, channels=1, rate=int(self.fs), output=True, stream_callback=self.callback, output_device_index=self.output_device_index, frames_per_buffer=1000)
			self.stream.start_stream()

	def write(self, string):
		self.outStr=""
		def addBitToQueue(bit, duration=1):
			self.outStr += "1" if bit else "0"
			self.queue.put((self.frequencyMark if bit else self.frequencySpace, duration))

		bs = string.encode(self.encoding)
		for bc in bs:
			if type(bc) == str:
				bc = ord(bc) # for python 2.x
			self.outStr += " " if self.outStr else ""
			parityState = self.parityOdd
			addBitToQueue(0) # START BIT
			for p in range(0, self.bits): # LSB ... MSB
				if 2**p & bc:
					addBitToQueue(1)
					parityState = not parityState
				else:
					addBitToQueue(0)

			if self.parity:
				addBitToQueue(1 if parityState else 0) # PARITY BIT

			addBitToQueue(1, self.stopBits) # STOP BIT

		print(self.outStr)

	def callback(self, in_data, frame_count, time_info, status):
		if self.bufferPreRoll:
			self.bufferPreRoll-=1
			return (self.outbuf, pyaudio.paContinue)

		start = time.time()

		for n in range(frame_count):
			if self.waitSamples > 0:
				self.waitSamples-=1
			else:
				try:
					f, d = self.queue.get_nowait()
					self.setFrequency(f)
					self.waitSamples = int(round(d * self.fs / self.baudRate))
				except:
					self.setFrequency(self.frequencyIdle)

			self.outbuf[n] = self.volume * np.sin(self.phase)

			# update phase for each sample
			self.phase+=self.deltaPhase
			if self.phase > 2*np.pi:
				self.phase-=2*np.pi

			# low pass filter for volume control
			if self.newVolume != None:
				self.volume, self.oldVolume = self.volume * 0.999 + self.newVolume * 0.001, self.volume
				if self.volume == self.oldVolume:
					self.volume, self.newVolume = self.newVolume, None

		# ~ print("#" * int((time.time() - start)*1000))
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

	def setBaudRate(self, baudRate):
		self.baudRate = baudRate

	def setEncoding(self, encoding):
		self.encoding = encoding

	def setParity(self, parityType):
		if parityType == "n":
			self.parity = False; self.parityOdd = False
		elif parityType == "e":
			self.parity = True; self.parityOdd = False
		elif parityType == "o":
			self.parity = True;  self.parityOdd = True
		else:
			raise Exception("setParity() should be called with 'o' or 'e' or 'n'!")

	def setVolume(self, volume):
		self.newVolume = volume

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

class MyQPlainTextEdit(QPlainTextEdit):
	keyPressWithControlPressed = pyqtSignal(int)
	def keyPressEvent(self, event):
		key = event.key()
		if event.modifiers() & Qt.CTRL:
			self.keyPressWithControlPressed.emit(key)
		else:
			QPlainTextEdit.keyPressEvent(self, event)

class GUI(QWidget):
	def __init__(self):
		QWidget.__init__(self)
		self.initUI()
		self.sound = SoundGenerator()

	def initUI(self):
		self.setStyleSheet("\
			QLabel { margin: 0px; padding: 0px; } \
			QPlainTextEdit { color: #00ff00; background: #000000; font-family: Monospace; font-size: 18px; } \
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

		# where we'll be typing stuff
		self.editor = MyQPlainTextEdit()
		self.editor.lastLen = 0
		self.editor.setWordWrapMode(QTextOption.NoWrap)
		self.editor.textChanged.connect(self.editorTextChanged)
		self.editor.keyPressWithControlPressed.connect(self.editorKeyWithControlPressed)
		self.editor.cursorPositionChanged.connect(lambda: self.editor.moveCursor(QTextCursor.End))
		layout.addWidget(self.editor)

		# encoding
		layout2 = QHBoxLayout()
		layout2.addWidget(QLabel("Character set / encoding :"))
		layout2.addStretch()
		self.encodingCombo = QComboBox()
		self.encodingCombo.insertItems(0, ['ascii', 'latin1', 'utf-8', 'utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be'])
		self.encodingCombo.setCurrentIndex(0)
		def fct():
			encoding = self.encodingCombo.currentText()
			if encoding.lower().startswith("utf-"):
				self.bitsCombo.setEditText('8')
			self.sound.setEncoding(encoding)
		self.encodingCombo.currentTextChanged.connect(fct)
		self.encodingCombo.setEditable(True)
		layout2.addWidget(self.encodingCombo)
		layout.addLayout(layout2)

		# baudrate
		layout2 = QHBoxLayout()
		layout2.addWidget(QLabel("Transmission rate (Bauds) :"))
		layout2.addStretch()
		self.baudRateCombo = QComboBox()
		self.baudRateCombo.insertItems(0, ['75', '300', '600', '1200'])
		self.baudRateCombo.setCurrentIndex(3)
		def fct():
			try:
				self.sound.setBaudRate(float(self.baudRateCombo.currentText()))
			except:
				self.baudRateCombo.setEditText("%g" % self.sound.baudRate)
		self.baudRateCombo.currentTextChanged.connect(fct)
		self.baudRateCombo.setEditable(True)
		layout2.addWidget(self.baudRateCombo)
		layout.addLayout(layout2)

		# bit per word
		layout2 = QHBoxLayout()
		layout2.addWidget(QLabel("Bits :"))
		layout2.addStretch()
		self.bitsCombo = QComboBox()
		self.bitsCombo.insertItems(0, ['7', '8'])
		self.bitsCombo.setCurrentIndex(0)
		def fct():
			try:
				self.sound.bits = int(self.bitsCombo.currentText())
			except:
				self.bitsCombo.setEditText("%d" % self.sound.bits)
		self.bitsCombo.currentTextChanged.connect(fct)
		self.bitsCombo.setEditable(True)
		layout2.addWidget(self.bitsCombo)
		layout.addLayout(layout2)

		# stop bit duration (in bits)
		layout2 = QHBoxLayout()
		layout2.addWidget(QLabel("Stop Bits :"))
		layout2.addStretch()
		self.stopBitsCombo = QComboBox()
		self.stopBitsCombo.insertItems(0, ['1', '1.5', '2'])
		self.stopBitsCombo.setCurrentIndex(0)
		def fct():
			try:
				self.sound.stopBits = float(self.stopBitsCombo.currentText())
			except:
				self.stopBitsCombo.setEditText("%d" % self.sound.stopBits)
		self.stopBitsCombo.currentTextChanged.connect(fct)
		layout2.addWidget(self.stopBitsCombo)
		layout.addLayout(layout2)

		# for each combobox
		for c in self.encodingCombo, self.baudRateCombo, self.bitsCombo, self.stopBitsCombo:
				c.setEditable(True)
				c.setMinimumContentsLength(5)
				c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

		# parity
		layout2 = QHBoxLayout()
		layout2.addWidget(QLabel("Parity :"))
		layout2.addStretch()
		self.parityNone = QRadioButton("None")
		self.parityOdd = QRadioButton("Odd")
		self.parityEven = QRadioButton("Even")
		self.parityEven.setChecked(True)

		radioGroup = QButtonGroup(self)
		def toggled():
			if self.parityNone.isChecked():
				self.sound.setParity("n")
			if self.parityOdd.isChecked():
				self.sound.setParity("o")
			if self.parityEven.isChecked():
				self.sound.setParity("e")

		for radio in self.parityNone, self.parityOdd, self.parityEven:
			radio.toggled.connect(toggled)
			radioGroup.addButton(radio)
			layout2.addWidget(radio)
		layout.addLayout(layout2)

		# sound
		layout2 = QHBoxLayout()
		self.v = QSlider(Qt.Horizontal)
		self.v.setToolTip("Adjust Volume")
		self.v.setMinimum(0)
		self.v.setMaximum(100)
		self.v.setValue(10)
		self.v.valueChanged.connect(lambda: self.sound.setVolume(self.v.value() / 100.0))
		layout2.addWidget(self.v)

		self.enableSoundCardBtn = mkButton("&Enable sound", layout2, self.enableSoundCardBtnClicked, isCheckable=True)
		layout.addLayout(layout2)

		self.setWindowTitle("V23 Sound Generator")
		self.show()
		self.setMaximumHeight(self.height())

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

	def editorTextChanged(self):
		err = False
		text = self.editor.toPlainText()

		i = self.editor.lastLen
		while i < len(text):
			try:
				c = text[i]
				if c == "\n":
					c="\r\n"
				self.sound.write(c)
				i+=1
			except Exception as e:
				print(c+":", e)
				text = text[:i] + text[i+1:]; err = True
		self.editor.lastLen = len(text)

		if err:
			self.editor.blockSignals(True)
			self.editor.setPlainText(text)
			self.editor.moveCursor(QTextCursor.End)
			self.editor.blockSignals(False)

	def editorKeyWithControlPressed(self, key):
		try:
			if key == Qt.Key_L: # clear screen
				self.sound.write("\x0c")
				self.editor.setPlainText("")
			elif key == Qt.Key_G: # bell
				self.sound.write("\x07")
			elif key == Qt.Key_Space:
				self.sound.write("\x00")
			elif Qt.Key_A <= key <= Qt.Key_Z:
				asc = key - Qt.Key_A + 1
				self.sound.write("%c" % asc)
		except Exception as e:
			print(e)

def main():
	app = QApplication(sys.argv)
	gui = GUI()
	ret = app.exec_()
	sys.exit(ret)

if __name__ == '__main__':
	main()

# clx.freeshell.org 2021
