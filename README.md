#Nysa Dionysus Platform

##Description:

An FPGA development board with a physical form factor similar to the standard
Arduino. In addition to the Arduino form factor the board has extra buttons
and LEDs as well as 8 MB of SDRAM and a high speed USB Interface with the host
computer. Developers can interface with Dionysus at multiple ways:

* Using the Nysa platform, users can choose from a selection of previously
  written Dionysus images to download then write python scripts to interface
  with Dionysus and all the devices attached to it.
* Using the Nysa platfrom, users can create their own image by using a simple
  JSON configuration file to generate a project that can be downloaded into
  Dionysus and then write Python scripts to interface in the same way as the
  previous step.
* Roll your own interface. The verilog modules/scripts to communicate through
  the USB chip are availabe in this package and in the nysa-verilog repo:
  http://github.com/CospanDesign/nysa-verilog

###Electrically
* The board can be powered using a 5V barrel jack similar to the
Arduino or like the Arduino the board can be completely powered by the USB.
* The board will accept 3.3V capable shields.

Because the board uses an FPGA instead of a MCU the board can interface
with a wider range of devices including cameras, LCD screens and devices
with non-standard protocols.


