
TOPLEVEL_LANG ?= verilog
PWD=$(shell pwd)
TOPDIR=$(PWD)/..
COCOTB 	:= $(shell $(python) nysa paths -c -s)
NYSA 	:= $(shell $(python) nysa paths -s -v nysa-verilog)
XILINX := $(shell $(python) nysa paths -s -x)
PYTHONPATH := ./model:$(PYTHONPATH)
export PYTHONPATH
export PYTHONHOME=$(shell python -c "from distutils.sysconfig import get_config_var; print(get_config_var('prefix'))")

EXTRA_ARGS+=-I$(TOPDIR)/rtl/ -I$(NYSA)/verilog/ -I$(TOPDIR)/sim/ -DSIMULATION

#Dependencies
VERILOG_SOURCES = $(NYSA)/verilog/wishbone/master/wishbone_master.v

VERILOG_SOURCES += ${NYSA}/verilog/generic/ppfifo.v
VERILOG_SOURCES += ${NYSA}/verilog/generic/bram.v
VERILOG_SOURCES += ${NYSA}/verilog/wishbone/slave/wb_bram/rtl/wb_bram.v
VERILOG_SOURCES += $(NYSA)/verilog/sim/wishbone/interconnect/example_2port_interconnect/wishbone_interconnect.v
VERILOG_SOURCES += ${TOPDIR}/sim/dionysus_sdram_tester.v
VERILOG_SOURCES += ${TOPDIR}/sim/arbiter_2_masters.v
VERILOG_SOURCES += ${TOPDIR}/sim/wishbone_mem_interconnect.v
VERILOG_SOURCES += ${TOPDIR}/sim/mt48lc4m16.v

VERILOG_SOURCES += ${TOPDIR}/rtl/dionysus_sdram.v
VERILOG_SOURCES += ${TOPDIR}/rtl/dionysus_sdram_clkgen.v
VERILOG_SOURCES += ${TOPDIR}/rtl/dionysus_sdram_read.v
VERILOG_SOURCES += ${TOPDIR}/rtl/dionysus_sdram_write.v
VERILOG_SOURCES += ${TOPDIR}/rtl/wb_dionysus_sdram.v



#DUT
#Test Benches
VERILOG_SOURCES += $(TOPDIR)/cocotb/tb_cocotb.v

TOPLEVEL = tb_cocotb

GPI_IMPL := vpi

export TOPLEVEL_LANG
MODULE=test_dut

include $(COCOTB)/makefiles/Makefile.inc
include $(COCOTB)/makefiles/Makefile.sim

.PHONY: wave test
wave:
	gtkwave waveforms.gtkw &


