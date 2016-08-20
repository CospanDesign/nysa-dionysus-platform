#! /usr/bin/python
# Copyright (c) 2013 Dave McCoy (dave.mccoy@cospandesign.com)

# This file is part of Nysa (wiki.cospandesign.com/index.php?title=Nysa).
#
# Nysa is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# any later version.
#
# Nysa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nysa; If not, see <http://www.gnu.org/licenses/>.

""" dionysus

Concrete interface for Nysa on the Dionysus platform
"""

__author__ = 'dave.mccoy@cospandesign.com (Dave McCoy)'

""" Changelog:
10/18/2013
    -Pep8ing the module and some cleanup
09/21/2012
    -added core dump function to retrieve the state of the master when a crash
    occurs
08/30/2012
    -Initial Commit
"""
import sys
import os
import Queue
import threading
import time
import gc
import atexit
from array import array as Array

from threading import current_thread


p = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.append(os.path.join(os.path.dirname(__file__),
                             os.pardir))

from nysa.host.nysa import Nysa
from nysa.common import status
from nysa.host.nysa import NysaCommError

#from pyftdi.pyftdi.ftdi import Ftdi
from ftdi import Ftdi
from array import array as Array

from bitbang.bitbang import BitBangController
import dionysus_utils


COMMAND_PING                = 0x0000
COMMAND_WRITE               = 0x0001
COMMAND_READ                = 0x0002
COMMAND_RESET               = 0x0003
COMMAND_MASTER_CFG_WRITE    = 0x0004
COMMAND_MASTER_CFG_READ     = 0x0005

FLAG_MEM_BUS                = 0x00010000
FLAG_DISABLE_AUTO_INC       = 0x00020000



DIONYSUS_QUEUE_TIMEOUT      = 7
DIONYSUS_PING_TIMEOUT       = 0.1
DIONYSUS_WRITE_TIMEOUT      = 5
DIONYSUS_READ_TIMEOUT       = 3
                            
INTERRUPT_COUNT             = 32
                            
MAX_WRITE_QUEUE_SIZE        = 10
MAX_READ_QUEUE_SIZE         = 10

#50 mS sleep between interrupt checks
INTERRUPT_SLEEP             = 0.050
#INTERRUPT_SLEEP = 1

DIONYSUS_RESET              = 1
DIONYSUS_WRITE              = 2
DIONYSUS_READ               = 3
DIONYSUS_PING               = 4
DIONYSUS_DUMP_CORE          = 5
DIONYSUS_IS_PROGRAMMED      = 6
                            
DIONYSUS_RESP_OK            = 0
DIONYSUS_RESP_ERR           = -1

_dionysus_instances = {}

def create_byte_array_from_dword(dword):
    d = Array('B')
    d.append((dword >> 24) & 0xFF)
    d.append((dword >> 16) & 0xFF)
    d.append((dword >>  8) & 0xFF)
    d.append((dword >>  0) & 0xFF)
    return d

def create_32bit_word(data_array, index = 0):
    return (data_array[index] << 24) | (data_array[index + 1] << 16) | (data_array[index + 2] << 8) | (data_array[index + 3])

def Dionysus(idVendor = 0x0403, idProduct = 0x8530, sernum = None, status = False):
    global _dionysus_instances
    if sernum in _dionysus_instances:
        return _dionysus_instances[sernum]
    _dionysus_instances[sernum] = _Dionysus(idVendor, idProduct, sernum, status)
    return _dionysus_instances[sernum]

class WorkerThread(threading.Thread):

    def __init__(self,
                 dev,
                 lock,
                 interrupt_update_callback):
        super(WorkerThread, self).__init__()
        self.dev = dev
        self.iuc = interrupt_update_callback
        self.lock = lock
        self.interrupts = 0

        self.interrupts_cb = []
        for i in range(INTERRUPT_COUNT):
            self.interrupts_cb.append([])

        self.finished = False
        atexit.register(self.kill_thread)

    def kill_thread(self):
        self.finished = True

    def run(self):
        while (not self.finished):
            time.sleep(INTERRUPT_SLEEP)
            if self.lock.acquire(False):
                self.check_interrupt()
                self.lock.release()

    def check_interrupt(self):
        self.interrupts = 0
        data = None
        try:
            data = self.dev.read_data_bytes(4, attempt=0)
            if len(data) == 0:
                return
            self.interrupts = create_32bit_word(data)
            if self.interrupts > 0:
                self.process_interrupts(self.interrupts)
                self.iuc(self.interrupts)

        except TypeError as ex:
            print "Type Error: %s" % str(ex)
        except IndexError:
            return
        except:
            print "Error while reading interrupts: %s" % sys.exc_info()[0]

    def process_interrupts(self, interrupts):
        for i in range(INTERRUPT_COUNT):
            if (interrupts & 1 << i) == 0:
                continue
            if len(self.interrupts_cb[i]) == 0:
                continue
            for cb in self.interrupts_cb[i]:
                try:
                    cb()
                except TypeError:
                    self.interrupts_cb.remove(cb)

    def register_interrupt_cb(self, index, cb):
        if index > INTERRUPT_COUNT - 1:
            raise NysaCommError("Index of interrupt device is out of range (> %d)" % (INTERRUPT_COUNT - 1))
        self.interrupts_cb[index].append(cb)

    def unregister_interrupt_cb(self, index, cb = None):
        if index > INTERRUPT_COUNT -1:
            raise NysaCommError("Index of interrupt device is out of range (> %d)" % (INTERRUPT_COUNT - 1))
        interrupt_list = self.interrupts_cb[index]
        if cb is None:
            interrupt_list = []

        elif cb in interrupt_list:
            interrupt_list.remove(cb)

class _Dionysus (Nysa):

    """
    Dionysus

    Concrete Class that implemented Dionysus specific communication functions
    """

    def __init__(self, idVendor = 0x0403, idProduct = 0x8530, sernum = None, status = False):
        Nysa.__init__(self, status)
        self.vendor = idVendor
        self.product = idProduct
        self.sernum = sernum

        self.dev = None
        #Run a full garbage collection so any previous references to Dionysus will be removed
        gc.collect()
        self.lock = threading.Lock()

        self.dev = Ftdi()
        self._open_dev()
        self.name = "Dionysus"
        self.interrupts = 0x00
        self.events = []
        for i in range (INTERRUPT_COUNT):
            e = threading.Event()
            e.set()
            self.events.append(e)


        self.worker = WorkerThread(self.dev,
                                   self.lock,
                                   self.interrupt_update_callback)
        #Is there a way to indicate closing
        self.worker.setDaemon(True)
        self.worker.start()

        try:
            #XXX: Hack to fix a strange bug where FTDI
            #XXX: won't recognize Dionysus until a read and reset occurs
            self.ping()
            pass

        except NysaCommError:
            pass

        #self.reset()
        self.sdb_read = False

    def _open_dev(self):
        """_open_dev

        Open an FTDI Communication Channel

        Args:
            Nothing

        Returns:
            Nothing

        Raises:
            Exception
        """
        #This frequency should go up to 60MHz
        frequency = 30.0E6
        #Latency can go down to 2 but there is a small chance there will be a
        #crash
        latency  = 2
        #Ftdi.add_type(self.vendor, self.product, 0x700, "ft2232h")
        self.dev.open(self.vendor, self.product, 0, serial = self.sernum)

        #Drain the input buffer
        self.dev.purge_buffers()

        #Reset
        #Configure Clock
        #XXX: Should this be chanced to 30MHz??
        #frequency = self.dev._set_frequency(frequency)

        #Set Latency Timer (XXX) This might be set by default
        self.dev.set_latency_timer(latency)

        #Set Chunk Size (Maximum Chunk size)
        self.dev.write_data_set_chunksize(0x10000)
        self.dev.read_data_set_chunksize(0x10000)

        #Set the hardware flow control
        self.dev.set_flowctrl('hw')
        self.dev.purge_buffers()
        #Enable MPSSE Mode
        self.dev.set_bitmode(0x00, Ftdi.BITMODE_SYNCFF)

    def sdb_read_callback(self):
        """sdb_read_callback
        
        Callback is called when SDB has been read and parsed

        Args:
            Nothing

        Returns:
            Nothing

        Raises:
            Exception
        """
        self.sdb_read = True

    def read(self, address, length = 1, disable_auto_inc = False):
        """read

        read data from Dionysus

        Command Format

        FF FF CC CC NN NN NN NN AA AA AA AA
        00 0? 00 02

            FF: Flags               (16-bits) 0x000?
            CC: Commands            (16-bits) 0x0002
            NN: Size of Writes      (32-bits) Number of 32-bit values
            AA: Address             (32-bits) 32-bit Address

        Args:
            address (long): Address of the register/memory to read
            length (int): Number of 32-bit words to read
            disable_auto_inc (bool): if true, auto increment feature will be
                disabled

        Returns:
            (Byte Array): A byte array containing the raw data returned from
            Dionysus

        Raises:
            NysaCommError
        """
        with self.lock:

            if self.sdb_read:
                self.mem_addr = self.nsm.get_address_of_memory_bus()

            command = COMMAND_READ

            if self.sdb_read and (address >= self.mem_addr):
                address = address - self.mem_addr
                command |= FLAG_MEM_BUS

            if disable_auto_inc:
                command |= FLAG_DISABLE_AUTO_INC

            write_data = Array('B')
            write_data.extend(create_byte_array_from_dword(command))
            write_data.extend(create_byte_array_from_dword(length))
            write_data.extend(create_byte_array_from_dword(address))

            self.dev.write_data(write_data)
            timeout = 2
            start = time.time()
            end = time.time()
            #read_data = Array('B')
            read_data = self.dev.read_data_bytes(length * 4, attempt = 5)
            #while ((end - start) > timeout) or (len(read_data) < length * 4):
            #    d = self.dev.read_data_bytes(length * 4, attempt = 4)
            #    if len(d) > 0:
            #        read_data.extend(d)
            #    end = time.time()

            #print "read data: %s" % str(read_data)
            return read_data

    def write(self, address, data, disable_auto_inc = False):
        """write

        Write data to a Nysa image

        Command Format

        FF FF CC CC NN NN NN NN AA AA AA AA DD DD DD DD ...
        00 0? 00 01

            FF: Flags               (16-bits)
            CC: Commands            (16-bits)
            NN: Size of Writes      (32-bits) Number of 32-bit values
            AA: Address             (32-bits) 32-bit Address
            DD: Data                (23-bits X Number of 32-bit values)

        Args:
            address (32-bit): Address of the register/memory to write to
            memory_device (boolean):
                True: Memory device
                False: Peripheral device
            data (array of bytes): Array of raw bytes to send to the devcie
            disable_auto_inc (boolean): Default False
                Set to true if only writing to one memory address (FIFO Mode)

        Returns: Nothing

        Raises:
            NysaCommError
        """

        with self.lock:

            write_data = Array('B')
            if self.mem_addr is None:
                self.mem_addr = self.nsm.get_address_of_memory_bus()

            command = COMMAND_WRITE

            if address >= self.mem_addr:
                address = address - self.mem_addr
                command |= FLAG_MEM_BUS

            if disable_auto_inc:
                command |= FLAG_DISABLE_AUTO_INC

            write_data.extend(create_byte_array_from_dword(command))

            while (len(data) % 4) != 0:
                data.append(0)

            data_count = len(data) / 4

            write_data.extend(create_byte_array_from_dword(data_count))
            write_data.extend(create_byte_array_from_dword(address))
            write_data.extend(data)

            if data_count == 0:
                raise NysaCommError("Length of data to write is 0!")

            self.dev.write_data(write_data)

    def ping (self):
        """ping

        Command Format

        FF FF CC CC
        00 00 00 00

        Args:
            Nothing

        Returns:
            Nothing

        Raises:
            NysaCommError
        """
        self.dev.write_data(Array('B', create_byte_array_from_dword(COMMAND_PING)))
        read_data = self.dev.read_data_bytes(4)

    def reset (self):
        """ reset

        Software reset the Nysa FPGA Master, this may not actually reset the entire
        FPGA image

        FF FF CC CC
        00 00 00 03

        Args:
            Nothing

        Return:
            Nothing

        Raises:
            NysaCommError: Failue in communication
        """
        with self.lock:
            bbc = BitBangController(self.vendor, self.product, 2)
            bbc.set_soft_reset_to_output()
            bbc.soft_reset_high()
            time.sleep(.2)
            bbc.soft_reset_low()
            time.sleep(.2)
            bbc.soft_reset_high()
            bbc.pins_on()
            bbc.set_pins_to_input()

    def is_programmed(self):
        """
        Check if the FPGA is programmed

        Args:
            Nothing

        Return (Boolean):
            True: FPGA is programmed
            False: FPGA is not programmed

        Raises:
            NysaCommError: Failue in communication
        """

        with self.lock:
            bbc = BitBangController(self.vendor, self.product, 2)
            done = bbc.read_done_pin()
            bbc.pins_on()
            bbc.set_pins_to_input()
            return done

    def dump_core(self):
        """ dump_core

        Returns the state of the wishbone master priorto a reset, this is usefu for
        statusging a crash

        Command Format

        XX XX XX XX

        Args:
            Nothing

        Returns:
            (Array of 32-bit Values) to be parsed by the core_analyzer utility

        Raises:
            NysaCommError: A failure in communication is detected
        """
        raise AssertionError("%s not implemented" % sys._getframe().f_code.co_name)

    def register_interrupt_callback(self, index, callback):
        """ register_interrupt

        Setup the thread to call the callback when an interrupt is detected

        Args:
            index (Integer): bit position of the device
                if the device is 1, then set index = 1
            callback: a function to call when an interrupt is detected

        Returns:
            Nothing

        Raises:
            Nothing
        """
        self.worker.register_interrupt_cb(index, callback)

    def unregister_interrupt_callback(self, index, callback = None):
        """ unregister_interrupt_callback

        Removes an interrupt callback from the reader thread list

        Args:
            index (Integer): bit position of the associated device
                EX: if the device that will receive callbacks is 1, index = 1
            callback: a function to remove from the callback list

        Returns:
            Nothing

        Raises:
            Nothing (This function fails quietly if ther callback is not found)
        """
        self.worker.unregister_interrupt_cb(index, callback)

    def wait_for_interrupts(self, wait_time = 1, dev_id = None):
        """ wait_for_interrupts

        listen for interrupts for the user specified amount of time

        The Nysa image will send a small packet of info to the host when a slave
        needs to send information to the host

        Response Format
        II II II II

        I: 32-bit interrupts bits, if bit 0 is set then slave 0 has an interrupt


        Args:
            wait_time (Integer): the amount of time in seconds to wait for an
                interrupt
            dev_id (Integer): Optional device id, if set the function will look
                if an interrupt has already been declared for that function, if
                so then return immediately otherwise setup a callback for this


        Returns (boolean):
            True: Interrupts were detected
            Falses: Interrupts were not detected

        Raises:
            NysaCommError: A failure in communication is detected
        """

        if dev_id is None:
            dev_id = 0

        e = self.events[dev_id]
        #print "Checking events!"

        with self.lock:
            #Check if we have interrupts
            if (self.interrupts & (1 << dev_id)) > 0:
                #There are already existing interrupts, we're done
                return True
            #if we don't have interrupts clear the associated event
            #Clear the event, the interrupt handler will unblock this
            e.clear()

        #Now wait for interrupts
        if e.wait(wait_time):
            #Received an interrupt
            return True
        #Timed out while waiting for interrupts
        e.set()
        return False

    def interrupt_update_callback(self, interrupts):
        #print "Entered interrupt update callback"
        self.interrupts = interrupts
        for i in range (INTERRUPT_COUNT):
            if i == 0:
                if not self.events[i].is_set():
                    #self.s.Debug( "interrupt!")
                    self.events[i].set()

            elif (self.interrupts & (1 << i)) > 0:
                if not self.events[i].is_set():
                    self.events[i].set()

    def get_board_name(self):
        return "Dionysus"

    def upload(self, filepath):
        dionysus_utils.upload(self.vendor, self.product, self.sernum, filepath, self.s)

    def program (self):
        dionysus_utils.program(self.vendor, self.product, self.sernum, self.s)

    def ioctl(self, name, arg = None):
        raise AssertionError("%s not implemented" % sys._getframe().f_code.co_name, self.s)

    def list_ioctl(self):
        raise AssertionError("%s not implemented" % sys._getframe().f_code.co_name, self.s)

    def get_sdb_base_address(self):
        return 0x00000000
