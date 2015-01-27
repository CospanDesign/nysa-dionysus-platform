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
from array import array as Array

from threading import current_thread


p = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.append(os.path.join(os.path.dirname(__file__),
                             os.pardir))

from nysa.host.nysa import Nysa
from nysa.common import status
from nysa.host.nysa import NysaCommError

#from pyftdi.pyftdi.ftdi import Ftdi

from pyftdi.pyftdi.ftdi import Ftdi
from array import array as Array

from bitbang.bitbang import BitBangController
import dionysus_utils


DIONYSUS_QUEUE_TIMEOUT = 7
DIONYSUS_PING_TIMEOUT = 0.1
DIONYSUS_WRITE_TIMEOUT = 5
DIONYSUS_READ_TIMEOUT = 3

INTERRUPT_COUNT = 32

MAX_WRITE_QUEUE_SIZE = 10
MAX_READ_QUEUE_SIZE = 10

#50 mS sleep between interrupt checks
INTERRUPT_SLEEP = 0.050
#INTERRUPT_SLEEP = 1

DIONYSUS_RESET = 1
DIONYSUS_WRITE = 2
DIONYSUS_READ = 3
DIONYSUS_PING = 4
DIONYSUS_DUMP_CORE = 5

DIONYSUS_RESP_OK = 0
DIONYSUS_RESP_ERR = -1

_dionysus_instances = {}

def Dionysus(idVendor = 0x0403, idProduct = 0x8530, sernum = None, status = False):
    global _dionysus_instances
    if sernum in _dionysus_instances:
        return _dionysus_instances[sernum]
    _dionysus_instances[sernum] = _Dionysus(idVendor, idProduct, sernum, status)
    return _dionysus_instances[sernum]

class DionysusData(object):
    data = None
    length = 0

class WorkerThread(threading.Thread):

    def __init__(   self,
                    dev,
                    host_write_queue,
                    host_read_queue,
                    dionysus_data,
                    lock,
                    interrupt_update_callback):
        super(WorkerThread, self).__init__()
        #self.name = "Worker"
        
        self.dev = dev
        self.hwq = host_write_queue
        self.hrq = host_read_queue
        self.iuc = interrupt_update_callback
        self.d = dionysus_data
        self.lock = lock
        self.interrupts = 0

        self.interrupts_cb = []
        for i in range(INTERRUPT_COUNT):
            self.interrupts_cb.append([])

    def last_ref(self):
        #self.s.Important("Last reference")
        self.hwq.put(None)

    def run(self):
        #self.s = status.Status()
        #self.s.set_level(status.StatusLevel.VERBOSE)
        #self.s.set_level(status.StatusLevel.FATAL)
        wdata = None
        rdata = None
        while (1):
            try:
                try:
                    wdata = self.hwq.get(block = True, timeout = INTERRUPT_SLEEP)
                    
                except Queue.Empty:
                    #Timeout has occured, read and process interrupts
                    #print ".",
                    self.check_interrupt()
                    continue 

                #Check for finish condition
                if wdata is None:
                    #if write data is None then we are done
                    return
                     
                if wdata == DIONYSUS_RESET:
                    self.reset()
                elif wdata == DIONYSUS_PING:
                    self.ping()
                elif wdata == DIONYSUS_WRITE:
                    self.write()
                elif wdata == DIONYSUS_READ:
                    self.read()
                elif wdata == DIONYSUS_DUMP_CORE:
                    self.dump_core()
                else:
                    print "Unrecognized command from write queue: %d" % wdata

            except AttributeError:
                print "closing dionysus worker thread"
                #If the queue is none then it was destroyed by the main thread
                #we are done then
                return

    def reset(self):
        vendor = self.d.data[0]
        product = self.d.data[1]
        bbc = BitBangController(vendor, product, 2)
        bbc.set_soft_reset_to_output()
        bbc.soft_reset_high()
        time.sleep(.2)
        bbc.soft_reset_low()
        time.sleep(.2)
        bbc.soft_reset_high()
        bbc.pins_on()
        bbc.set_pins_to_input()
        self.hrq.put(DIONYSUS_RESP_OK)

    def write(self):
        self.dev.purge_buffers()
        self.dev.write_data(self.d.data)

        rsp = Array ('B')
        #self.s = True
        #if self.s and (len(self.d.data) < 100):
        #    self.s.Debug( "Data Out: %s" % str(self.d.data))

        #rsp = Array ('B')
        rsp = self.dev.read_data_bytes(1)

        if len(rsp) > 0 and rsp[0] == 0xDC:
            #self.s.Debug( "Got a Response")
            pass
        else:
            timeout = time.time() + DIONYSUS_WRITE_TIMEOUT
            while time.time() < timeout:
                rsp = self.dev.read_data_bytes(1)
                if len(rsp) > 0 and rsp[0] == 0xDC:
                    #self.s.Debug( "Got a Response")
                    break

        if len(rsp) > 0:
            if rsp[0] != 0xDC:
                #self.s.Error( "Reponse ID Not found")
                #raise NysaCommError("Did not find ID byte (0xDC) in response: %s" % str(rsp))
                self.hrq.put(DIONYSUS_RESP_ERR)
                return

        else:
            #self.s.Error("No Response")
            #raise NysaCommError ("Timeout while waiting for response")
            self.hrq.put(DIONYSUS_RESP_ERR)
            return


        #Got ID byte now look for the rest of the data
        read_count = 0
        rsp = self.dev.read_data_bytes(12)
        timeout = time.time() + DIONYSUS_WRITE_TIMEOUT
        read_count = len(rsp)

        while (time.time() < timeout) and (read_count < 12):
            rsp += self.dev.read_data_bytes(12 - read_count)
            read_count = len(rsp)

        #self.s.Debug( "DEBUG: Write Response: %s" % str(rsp[0:8]))
        #self.s.Debug( "Response: %s" % str(rsp))

        self.hrq.put(DIONYSUS_RESP_OK)

    def read(self):
        length = self.d.length
        self.dev.purge_buffers()
        dout = self.d.data
        #self.s.Debug( "READ Request: Data Out: %s" % str(self.d.data))

        self.dev.write_data(self.d.data)

        rsp = Array ('B')
        rsp = self.dev.read_data_bytes(2)
        if len(rsp) > 1 and rsp[0] == 0xDC and rsp[1] == 0xFD:
            #if self.s: self.s.Debug("Got a Response")
            pass
        else:
            timeout = time.time() + DIONYSUS_READ_TIMEOUT
            while time.time() < timeout:
                rsp = self.dev.read_data_bytes(1)
                if len(rsp) > 0 and rsp[0] == 0xDC:
                    #if self.s: self.s.Debug( "Got a Response")
                    break

        if len(rsp) > 0:
            if rsp[0] != 0xDC:
                #if self.s:
                #    self.s.Error("Response Not Found")
                #raise NysaCommError("Did not find identification byte (0xDC): %s" % str(rsp))
                self.hrq.put(DIONYSUS_RESP_ERR)
                return

        else:
            #if self.s:
            #    self.s.Error("Timed out while waiting for response")
            #raise NysaCommError("Timeout while waiting for a response")
            self.hrq.put(DIONYSUS_RESP_ERR)
            return

        #print "finished"
        #Watch out for the modem status bytes
        rsp = rsp[1:]
        read_count = len(rsp)
        timeout = time.time() + DIONYSUS_READ_TIMEOUT

        total_length = length * 4 + 8
        rsp += self.dev.read_data_bytes(total_length - read_count)
        read_count = len(rsp)
        
        while (time.time() < timeout) and (read_count < total_length):
            rsp += self.dev.read_data_bytes(total_length - read_count)
            read_count = len(rsp)

        #self.s = True
        '''
        if self.s:
            self.s.Debug("DEBUG READ:")
            if (time.time() > timeout):
                self.d.Error("\tTimeout condition occured!")
            self.s.Debug( "Time left on timeout: %d" % (timeout - time.time()))

            self.s.Debug( "\tResponse Length: %d" % len(rsp))
            self.s.Debug( "\tResponse Status: %s" % str(rsp[:8]))
            self.s.Debug( "\tResponse Dev ID: %d Addr: 0x%06X" % (rsp[4], (rsp[5] << 16 | rsp[6] << 8 | rsp[7])))
            if len(rsp[8:]) > 32:
                #self.s.Debug( "\tResponse Data:\n\t%s" % str(rsp[8:40]))
                self.s.Debug( "\tResponse Data:\n\t%s" % str(rsp[:40]))
            else:
                self.s.Debug( "\tResponse Data:\n\t%s" % str(rsp))
        '''
        #self.s = False
        #self.s = False
        self.d.data = rsp[8:]
        self.hrq.put(DIONYSUS_RESP_OK)

    def ping(self):
        data = Array('B')
        data.extend([0xCD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        #if self.s:
        #    self.s.Debug( "Sending ping...",)


        self.dev.write_data(data)

        #Set up a response
        rsp = Array('B')
        temp = Array('B')

        timeout = time.time() + DIONYSUS_PING_TIMEOUT

        while time.time() < timeout:
            rsp = self.dev.read_data_bytes(5)
            temp.extend(rsp)
            if 0xDC in rsp:
                #if self.s:
                #    self.s.Debug( "Response to Ping")
                #    self.s.Debug( "Resposne: %s" % str(temp))
                break

        if not 0xDC in rsp:
            #if self.s:
            #    self.s.Debug( "ID byte not found in response")
            #raise NysaCommError("Ping response did not contain ID: %s" % str(temp))
            self.hrq.put(DIONYSUS_RESP_ERR)
            return

        index = rsp.index (0xDC) + 1
        read_data = Array('B')
        read_data.extend(rsp[index:])

        num = 3 - index
        read_data.extend(self.dev.read_data_bytes(num))

        #if self.s:
        #    self.s.Debug( "Success")

        self.hrq.put(DIONYSUS_RESP_OK)

    def dump_core(self):
        data = Array ('B')
        data.extend([0xCD, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        #if self.s:
        #    self.s.Debug( "Sending core dump request...")

        self.dev.purge_buffers()
        self.dev.write_data(data)

        core_dump = Array('L')
        wait_time = 5
        timeout = time.time() + wait_time

        temp = Array ('B')
        while time.time() < timeout:
            rsp = self.dev.read_data_bytes(1)
            temp.extend(rsp)
            if 0xDC in rsp:
                #self.s.Debug( "Read a response from the core dump")
                break

        if not 0xDC in rsp:
            #if self.s:
            #    self.s.Debug( "Response not found!")
            raise NysaCommError("Response Not Found")

        rsp = Array ('B')
        read_total = 4
        read_count = len(rsp)

        #Get the number of items from the incomming data, This size is set by the
        #Wishbone Master
        timeout = time.time() + wait_time
        while (time.time() < timeout) and (read_count < read_total):
            rsp += self.dev.read_data_bytes(read_total - read_count)
            read_count = len(rsp)


        count = (rsp[1] << 16 | rsp[2] << 8 | rsp[3]) * 4
        '''
        if self.s:
            self.s.Debug( "Length of read:%d" % len(rsp))
            self.s.Debug( "Data: %s" % str(rsp))
            self.s.Debug( "Number of core registers: %d" % (count / 4))
        '''

        timeout = time.time() + wait_time
        read_total = count
        read_count = 0
        temp = Array ('B')
        rsp = Array('B')
        while (time.time() < timeout) and (read_count < read_total):
            rsp += self.dev.read_data_bytes(read_total - read_count)
            read_count = len(rsp)

        #if self.s:
        #    self.s.Debug( "Length read: %d" % (len(rsp) / 4))
        #    self.s.Debug( "Data: %s" % str(rsp))

        core_data = Array('L')
        '''
        for i in range(0, count, 4):
            if self.s:
                self.s.Debug( "Count: %d" % i)
                core_data.append(rsp[i] << 24 | rsp[i + 1] << 16 | rsp[i + 2] << 8 | rsp[i + 3])


        if self.s:
            self.s.Debug( "Core Data: %s" % str(core_data))
        '''

        self.d.data = core_data
        self.hrq.put(DIONYSUS_RESP_OK)

    def check_interrupt(self):
        self.interrupts = 0
        data = None
        if not self.lock.acquire(False):
            #Could not aquire lock, return
            return
            
        try:
            data = self.dev.read_data_bytes(2)
            if len(data) == 0 or data[0] != 0xDC:
                return

            data += self.dev.read_data_bytes(11)
            
            #self.s.Verbose("data: %s" % str(data))

            if len(data) != 13:
                print "data length is not 13!: %s" % str(data)
            
            self.interrupts =   (data[9]  << 24 |
                                data[10] << 16 |
                                data[11] << 8  |
                                data[12])

            if self.interrupts > 0:
                self.process_interrupts(self.interrupts)
                self.iuc(self.interrupts)
                #print "Interrupt finished"

        except TypeError as ex:
            print "Type Error: %s" % str(ex)
        except:
            print "Error while reading interrupts: %s" % sys.exc_info()[0]
            #print "Exception when reading interrupts"

        finally:
            self.lock.release()

    def process_interrupts(self, interrupts):
        for i in range(INTERRUPT_COUNT):
            if (interrupts & 1 << i) == 0:
                continue
            if len(self.interrupts_cb[i]) == 0:
                continue
            #Call all callbacks
            #self.s.Debug( "Calling callback for: %d" % i)
            for cb in self.interrupts_cb[i]:
                try:
                    #print "callback %s" % str(cb)
                    cb()
                except TypeError:
                    #If an error occured when calling a callback removed if from
                    #our list
                    self.interrupts_cb.remove(cb)
                    #self.s.Debug( "Error need to remove callback")

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

        self.hwq = Queue.Queue(10)
        self.hrq = Queue.Queue(10)

        self.d = DionysusData()

        self.worker = WorkerThread(self.dev,
                                   self.hwq,
                                   self.hrq,
                                   self.d,
                                   self.lock,
                                   self.interrupt_update_callback)
        #Is there a way to indicate closing
        self.worker.setDaemon(True)
        self.worker.start()

        try:
            #XXX: Hack to fix a strange bug where FTDI
            #XXX: won't recognize Dionysus until a read and reset occurs
            self.ping()

        except NysaCommError:
            pass

        self.reset()



        '''
        #status = True
        self.reader_thread = ReaderThread(self.dev, self.interrupt_update_callback, self.lock, status = status)
        self.reader_thread.setName("Reader Thread")
        #XXX: Need to find a better way to shut this down
        self.reader_thread.setDaemon(True)
        self.reader_thread.start()
        '''

    def __del__(self):
        #if self.s: self.s.Debug( "Close reader thread")
        #self.lock.aquire()
        #if (self.reader_thread is not None) and self.reader_thread.isAlive():
        #    self.reader_thread.stop()
        #    self.s.Debug( "Waiting to join")
        #    self.reader_thread.join()
        #self.lock.release()
        #self.s = True
        #if self.s: self.s.Debug( "Reader thread joined")
        #self.dev.close()
        pass

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
        #frequency = self.dev._set_frequency(frequency)

        #Set Latency Timer
        self.dev.set_latency_timer(latency)

        #Set Chunk Size (Maximum Chunk size)
        self.dev.write_data_set_chunksize(0x10000)
        self.dev.read_data_set_chunksize(0x10000)

        #Set the hardware flow control
        self.dev.set_flowctrl('hw')
        self.dev.purge_buffers()
        #Enable MPSSE Mode
        self.dev.set_bitmode(0x00, Ftdi.BITMODE_SYNCFF)

    def ipc_comm_response(self, name):
        try:
            resp = self.hrq.get(block = True, timeout = DIONYSUS_QUEUE_TIMEOUT)
            if resp == DIONYSUS_RESP_OK:
                #print "%s got an OK response!" % current_thread().name
                return self.d.data
            else:
                raise NysaCommError("Dionysus response error %s: %d" % (name, resp))
        except Queue.Empty:
            raise NysaCommError("Dionysus error %s: timeout: %d" % (name, DIONYSUS_QUEUE_TIMEOUT))

    def read(self, address, length = 1, memory_device = False, disable_auto_inc = False):
        """read

        read data from Dionysus

        Command Format

        ID 02 NN NN NN OO AA AA AA
           ID: ID Byte (0xCD)
           02: Read Command (12 for memory read)
           NN: Size of Read (3 Bytes)
           OO: Offset (for peripheral, part of address for mem)
           AA: Address (3 bytes for peripheral,
               (4 bytes including offset for mem)

        Args:
            address (int): Address of the register/memory to read
            memory_device (boolean): True if the device is on the memory bus
            length (int): Number of 32-bit words to read

        Returns:
            (Byte Array): A byte array containing the raw data returned from
            Dionysus

        Raises:
            NysaCommError
        """
        #self.s = True
        #print "%s: read: lock state (locked == true): %s" % (current_thread().name, str(self.lock.locked()))
        with self.lock:
            #print "lock acquired for read"
            #if self.s: self.s.Debug( "Reading...")
            
            #Set up the ID and the 'Read command (0x02)'
            self.d.data = Array('B', [0xCD, 0x02])
            if memory_device:
                #if self.s:
                #    self.s.Debug( "Read from Memory Device")
                #'OR' the 0x10 flag to indicate that we are using the memory bus
                #self.d.data = Array('B', [0xCD, 0x12])
                self.d.data[1] = self.d.data[1] | 0x10

            if disable_auto_inc:
                self.d.data[1] = self.d.data[1] | 0x20
            
            #Add the length value to the array
            fmt_string = "%06X" % length
            self.d.data.fromstring(fmt_string.decode('hex'))
            
            #Add the device Number
            
            #XXX: Memory devices don't have an offset (should they?)
            
            #Add the address
            addr_string = "%08X" % address
            self.d.data.fromstring(addr_string.decode('hex'))
            #self.s.Debug( "DEBUG: Data read string: %s" % str(self.d.data))
            
            self.d.length = length
            self.hwq.put(DIONYSUS_READ)
            return self.ipc_comm_response("read")

    def write(self, address, data, memory_device=False, disable_auto_inc = False):
        """write

        Write data to a Nysa image

        Command Format

        ID 01 NN NN NN OO AA AA AA DD DD DD DD
           ID: ID Byte (0xCD)
           01: Write Command (11 for Memory Write)
           NN: Size of Write (3 Bytes)
           OO: Offset (for peripheral, part of address for mem)
           AA: Address (3 bytes for peripheral,
             #(4 bytes including offset for mem)
           DD: Data (4 bytes)

        Args:
            address (int): Address of the register/memory to write to
            memory_device (boolean):
                True: Memory device
                False: Peripheral device
            data (array of bytes): Array of raw bytes to send to the devcie

        Returns: Nothing

        Raises:
            NysaCommError
        """
        #print "%s: write: lock state (locked == true): %s" % (current_thread().name, str(self.lock.locked()))
        with self.lock:
            #print "lock acquired for write"
            length = len(data) / 4
            #Create an Array with the identification byte and code for writing
            self.d.data = Array ('B', [0xCD, 0x01])
            if memory_device:
                '''
                if self.s:
                    self.s.Debug( "Memory Device")
                '''
                #self.d.data = Array('B', [0xCD, 0x11])
                self.d.data[1] = self.d.data[1] | 0x10
            if disable_auto_inc:
                self.d.data[1] = self.d.data[1] | 0x20
            
            #Append the length into the first 24 bits
            fmt_string = "%06X" % length
            self.d.data.fromstring(fmt_string.decode('hex'))
            addr_string = "%08X" % address
            self.d.data.fromstring(addr_string.decode('hex'))
            self.d.data.extend(data)
            '''
            if self.s:
                self.s.Debug( "Length: %d" % len(data))
                self.s.Debug( "Reported Length: %d" % length)
                self.s.Debug( "Writing: %s" % str(self.d.data[0:9]))
                self.s.Debug( "\tData: %s" % str(self.d.data[9:13]))
            '''
            
            self.hwq.put(DIONYSUS_WRITE)
            self.ipc_comm_response("write")

    def ping (self):
        """ping

        Command Format

        ID 00 00 00 00 00 00 00 00
            ID: ID Byte (0xCD)
            00: Ping Command
            00 00 00 00 00 00 00: Zeros

        Args:
            Nothing

        Returns:
            Nothing

        Raises:
            NysaCommError
        """
        with self.lock:
            self.hwq.put(DIONYSUS_PING)
            self.ipc_comm_response("ping")

    def reset (self):
        """ reset

        Software reset the Nysa FPGA Master, this may not actually reset the entire
        FPGA image

        ID 03 00 00 00
            ID: ID Byte (0xCD)
            00: Reset Command
            00 00 00: Zeros

        Args:
            Nothing

        Return:
            Nothing

        Raises:
            NysaCommError: Failue in communication
        """
        with self.lock:
            self.d.data = (self.vendor, self.product)
            self.hwq.put(DIONYSUS_RESET)
            self.ipc_comm_response("reset")

    def dump_core(self):
        """ dump_core

        Returns the state of the wishbone master priorto a reset, this is usefu for
        statusging a crash

        Command Format

        ID 0F 00 00 00 00 00 00 00
            ID: ID Byte (0xCD)
            0F: Dump Core Command
            00 00 00 00 00 00 00 00 00 00 00: Zeros

        Args:
            Nothing

        Returns:
            (Array of 32-bit Values) to be parsed by the core_analyzer utility

        Raises:
            NysaCommError: A failure in communication is detected
        """
        with self.lock:
            self.hwq.put(DIONYSUS_DUMP_CORE)
            return self.ipc_comm_response("dump core")

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
        #self.reader_thread.register_interrupt_cb(index, callback)

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
        #self.reader_thread.unregister_interrupt_cb(index, callback)

    def wait_for_interrupts(self, wait_time = 1, dev_id = None):
        """ wait_for_interrupts

        listen for interrupts for the user specified amount of time

        The Nysa image will send a small packet of info to the host when a slave
        needs to send information to the host

        Response Format
        DC 01 00 00 00 II II II II
            DC: Inverted CD is the start of a response
            01: Interrupt ID
            00 00 00 00 00 00 00 00: Zeros, reserved for future use
            II II II II: 32-bit interrupts


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
                #self.s.Debug( "Found existing interrupts")
                return True
            #if we don't have interrupts clear the associated event
            e.clear()

        #print "Waiting for interrupts"
        if e.wait(wait_time):
            #print "Found interrupts!"
            #self.s.Debug( "Found interrupts")
            return True
        #print "did not find interrupts"
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
