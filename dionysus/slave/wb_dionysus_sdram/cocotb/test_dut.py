# Simple tests for an adder module
import os
import sys
import cocotb
import logging
from cocotb.result import TestFailure
from cocotb.triggers import RisingEdge
from cocotb.triggers import ReadOnly
from nysa.host.sim.sim_host import NysaSim
from cocotb.clock import Clock
import time
from array import array as Array
from dut_driver import wb_dionysus_sdramDriver

SIM_CONFIG = "sim_config.json"


CLK_PERIOD = 10
SDRAM_CLK_PERIOD = 5

MODULE_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "rtl")
MODULE_PATH = os.path.abspath(MODULE_PATH)


def setup_dut(dut):
    cocotb.fork(Clock(dut.m0.ram.clkgen.sim_clk, SDRAM_CLK_PERIOD).start())

@cocotb.test(skip = False)
def first_test(dut):
    """
    Description:
        Very Basic Functionality
            Startup Nysa

    Test ID: 0

    Expected Results:
        Write to all registers
    """
    #Use the folowing value to find the test in the simulation (It should show up as the yellow signal at the top of the waveforms)
    dut.test_id = 0
    print "module path: %s" % MODULE_PATH
    print "initializing nysa sim"
    setup_dut(dut)
    nysa = NysaSim(dut, SIM_CONFIG, CLK_PERIOD, user_paths = [MODULE_PATH])
    print "done"

    yield (nysa.reset())
    yield (nysa.wait_clocks(60))
    yield (nysa.reset())
    nysa.read_sdb()
    yield (nysa.wait_clocks(10))
    nysa.pretty_print_sdb()
    #driver = wb_dionysus_sdramDriver(nysa, nysa.find_device(wb_dionysus_sdramDriver)[0])
    dut.log.info("Ready")

    #For a demo write a value to the control register (See the wb_dionysus_sdramDriver for addresses)
    #WRITE_VALUE = 0x01
    #dut.log.info("Writing value: 0x%08X" % WRITE_VALUE)
    #yield cocotb.external(driver.set_control)(WRITE_VALUE)
    yield (nysa.wait_clocks(100))

    yield cocotb.external(nysa.write_memory)(0x00, [0x00, 0x01, 0x02, 0x03])
    dut.log.info("Reading value...")
    yield (nysa.wait_clocks(10))

    read_data = yield cocotb.external(nysa.read_memory)(0x00, 1)
    dut.log.info("Control Register: 0x%08X" % str(read_data))

